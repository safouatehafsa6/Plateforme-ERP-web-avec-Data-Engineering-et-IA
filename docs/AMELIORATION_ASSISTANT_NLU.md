# Amélioration de la compréhension du chatbot ERP

## Objectif

Améliorer la compréhension des intentions formulées de différentes manières, sans remplacer les workflows ERP existants ni laisser le modèle exécuter directement des requêtes SQL.

## Changements

- Ajout d'une couche NLU dans `backend/app/routers/assistant.py`.
- Classification optionnelle via une API compatible OpenAI, configurée avec `OPENAI_API_KEY`, `OPENAI_BASE_URL` et `OPENAI_MODEL`.
- Mode de secours multilingue sans clé API pour reconnaître notamment « créer une commande », « faire une commande », « passer une commande » et « make an order ».
- Extraction prudente de certaines entités (nom du client, produit, quantité, e-mail) quand elles sont explicitement présentes.
- Si un nom de client est extrait pour une commande, il est recherché dans la base de données de l'entreprise connectée; l'identifiant n'est jamais accepté directement depuis le modèle.
- Les workflows multi-étapes actifs ne sont pas reclassifiés à chaque réponse de l'utilisateur.
- Les opérations d'écriture restent dans le backend existant, avec vérification des permissions et confirmation avant la création de la commande.
- Si le fournisseur LLM est indisponible, le chatbot revient au moteur de règles au lieu d'interrompre la conversation.

## Configuration facultative du LLM

Dans le fichier `.env` à la racine, ajouter une clé valide si l'utilisation d'un fournisseur externe est autorisée :

```dotenv
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Sans `OPENAI_API_KEY`, seul le moteur de secours par règles/synonymes est actif. Une clé API n'est pas incluse dans le dépôt. Si un fournisseur externe est configuré, le texte des messages est envoyé à ce fournisseur; vérifier les règles de confidentialité applicables avant d'activer cette option en production.

## Tests

Des tests unitaires ont été ajoutés dans `backend/tests/test_assistant_intent.py` pour couvrir les paraphrases de création de commande, les intentions client/fournisseur, l'extraction d'un nom de client et le rejet d'un message sans intention métier claire.

Avant de considérer l'amélioration comme terminée, exécuter les tests dans l'environnement du backend, puis tester manuellement le dialogue dans Docker et vérifier que les workflows de création/confirmation existants fonctionnent toujours.
