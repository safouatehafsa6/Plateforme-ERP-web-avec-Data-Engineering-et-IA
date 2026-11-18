# Déploiement VMware — OCR, dictée et IA locale

## 1. Préserver la configuration existante

- Conserver le fichier `.env` local déjà utilisé : ne pas le remplacer par `.env.example`.
- Le fichier `.env` contient des secrets (JWT, mots de passe et clés) : ne pas le publier sur GitHub.
- Les valeurs par défaut ajoutées dans Compose sont adaptées à une VM modeste : 6 000 caractères envoyés au modèle, délai IDP de 600 secondes et désactivation de la seconde passe de structure libre. Les valeurs peuvent être surchargées dans `.env`.

## 2. Identifier où tourne Ollama

### Cas A — Docker et Ollama tournent dans la même machine (Windows ou VM Linux)

La configuration par défaut utilise :

`http://host.docker.internal:11434/v1`

Sous Docker Engine Linux, `extra_hosts: host.docker.internal:host-gateway` est déclaré dans Compose pour résoudre ce nom depuis le conteneur.

### Cas B — Docker tourne dans la VM VMware et Ollama tourne sur Windows hôte

`host.docker.internal` désigne généralement la machine qui exécute Docker (la VM), pas nécessairement Windows. Il faut donc utiliser l'adresse IP de l'hôte Windows joignable depuis la VM.

1. Sur Windows, relever l'adresse de l'interface VMware/VMnet8 joignable depuis la VM (`ipconfig`).
2. Vérifier que la VM peut joindre cette adresse.
3. Dans `.env`, définir `RAG_LLM_BASE_URL=http://IP_WINDOWS_HOTE:11434/v1`.
4. Configurer Ollama sur Windows pour écouter sur une interface accessible (`OLLAMA_HOST=0.0.0.0:11434`) et autoriser TCP 11434 dans le pare-feu Windows uniquement depuis le réseau privé VMware.
5. Ne pas exposer le port Ollama à Internet.

Si la VM ne peut pas joindre l'hôte, corriger d'abord le réseau VMware (NAT/VMnet8, passerelle et pare-feu) : le code ERP ne peut pas contourner une absence de connectivité.

## 3. Installation du modèle sur la machine Ollama

```bash
ollama pull qwen2.5:3b
ollama list
```

Vérifier l'API depuis la machine qui héberge Ollama :

```bash
curl http://localhost:11434/api/tags
```

Puis depuis le conteneur backend :

```bash
docker compose exec backend python -c "import os,urllib.request; u=(os.getenv('RAG_LLM_BASE_URL') or 'http://host.docker.internal:11434/v1').rstrip('/'); print(urllib.request.urlopen(u + '/models', timeout=10).status)"
```

Le test reprend automatiquement `RAG_LLM_BASE_URL` lorsqu'elle est définie ; sinon il utilise l'adresse par défaut.

## 4. Construire et lancer

À la racine du projet :

```bash
docker compose config
docker compose up -d --build backend frontend
docker compose ps
docker compose logs --tail=100 backend
```

Les images Docker du backend installent Tesseract avec les packs `fra`, `ara` et `eng`. Aucun Tesseract Windows n'est requis lorsque le backend tourne dans Docker.

## 5. Vérifications fonctionnelles

```bash
docker compose exec backend python -m unittest tests.test_idp -v
docker compose exec backend python -m unittest tests.test_assistant_reformulation -v
```

Dans l'ERP :
- importer un PDF numérisé ou une image contenant du texte français, arabe ou anglais ;
- vérifier que le document indique si l'OCR a été utilisé, puis contrôler/corriger les champs avant validation ;
- ouvrir un champ texte IDP, cliquer sur le microphone, dicter, puis corriger ou reformuler ;
- appliquer la proposition IA uniquement après vérification ;
- tester depuis un écran mobile et vérifier les formulaires et tableaux avec défilement horizontal localisé.

## 6. Limites à connaître

- La dictée utilise l'API Web Speech du navigateur. Elle dépend du navigateur, de la permission microphone et d'une origine sécurisée (HTTPS ou localhost). Chrome/Edge sont les choix les plus compatibles ; certains navigateurs mobiles ne fournissent pas cette API.
- La correction et la reformulation nécessitent que le modèle Ollama soit démarré et accessible depuis le backend.
- Une proposition OCR/IA doit toujours être vérifiée par un utilisateur avant validation ou intégration métier.
