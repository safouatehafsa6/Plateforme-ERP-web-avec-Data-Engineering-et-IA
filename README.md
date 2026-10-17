# Environnement conteneurisé — Plateforme ERP intelligente

Cet environnement permet à chaque membre du binôme de lancer exactement les
mêmes services (base de données, data lake, orchestration, traitement
distribué) sans rien installer manuellement sur sa machine, à part Docker.

## Prérequis (une seule fois par personne)

1. Installer **Docker Desktop** (Windows/Mac) ou **Docker Engine + Docker
   Compose** (Linux) : https://docs.docker.com/get-docker/
2. Vérifier l'installation :
   ```bash
   docker --version
   docker compose version
   ```

## Démarrage rapide

```bash
# 1. Cloner le dépôt GitHub partagé
git clone <url-du-repo>
cd erp-project

# 2. Créer votre fichier de configuration local
cp .env.example .env

# 3. Lancer tous les services en arrière-plan
docker compose up -d

# 4. Vérifier que tout tourne
docker compose ps
```

## Services disponibles et leurs URLs

| Service              | URL / port              | Identifiants par défaut       |
|----------------------|--------------------------|--------------------------------|
| Base de données ERP  | localhost:5432           | erp_user / erp_password        |
| MinIO (console web)  | http://localhost:9001    | minio_admin / minio_password   |
| MinIO (API S3)       | http://localhost:9000    | —                               |
| Airflow (interface)  | http://localhost:8080    | admin / admin                  |
| Spark master (UI)    | http://localhost:8081    | —                               |

Les buckets `raw`, `staging` et `curated` sont créés automatiquement dans
MinIO au premier démarrage (zones du data lake).

## Commandes utiles au quotidien

```bash
# Voir les logs d'un service en direct
docker compose logs -f airflow-webserver

# Redémarrer un seul service après une modification
docker compose restart backend

# Arrêter tout sans supprimer les données
docker compose stop

# Arrêter et supprimer les conteneurs (les données persistent dans les volumes)
docker compose down

# Tout supprimer y compris les données (repartir de zéro)
docker compose down -v
```

## Prochaines étapes pour le binôme

1. **Backend** : ajoutez votre code dans `./backend`, avec un `Dockerfile`,
   puis décommentez le service `backend` dans `docker-compose.yml`.
2. **Frontend** : même principe dans `./frontend`, puis décommentez le
   service `frontend`.
3. **Pipelines Airflow** : placez vos fichiers Python de DAGs dans
   `./airflow/dags` — ils apparaissent automatiquement dans l'interface
   Airflow (aucun redémarrage nécessaire).
4. **Travail en équipe** : chaque personne travaille sur son code localement,
   commit/push sur le dépôt Git partagé. Celui qui récupère les changements
   (`git pull`) relance simplement `docker compose up -d --build` pour que
   son environnement reflète les derniers changements.

## Bonnes pratiques

- Ne modifiez jamais directement un conteneur en cours d'exécution : modifiez
  le code source ou le `docker-compose.yml`, puis relancez.
- Committez `docker-compose.yml`, `.env.example` et ce README dans Git.
- Ne committez **jamais** le fichier `.env` réel (mots de passe).
- En cas de comportement étrange, `docker compose down -v` puis
  `docker compose up -d` repart d'un environnement propre.
# Module métier Achats

Cette version ajoute la chaîne achats :

**Demande d'achat → Bon de commande fournisseur → Réception**

## Ce qui a été ajouté

### Backend
- Migration tenant `012_achats_metier.sql`.
- Tables `demande_achat`, `ligne_demande_achat`, `reception_achat` et `ligne_reception_achat`.
- Extension de la table existante `achat` avec numéro métier, lien vers la demande, notes et date de modification.
- API FastAPI `/api/achats` avec contrôle RBAC et isolation par base entreprise.
- Consultation des fournisseurs et produits de l'entreprise.
- Création et soumission des demandes d'achat.
- Conversion d'une demande soumise en bon de commande fournisseur.
- Création directe d'un bon de commande fournisseur.
- Réceptions partielles ou complètes.
- Mise à jour transactionnelle du stock à chaque réception.
- Création d'un `mouvement_stock` de type `entree` pour assurer la traçabilité.

### Frontend
- Nouvelle page React `/achats`.
- Lien **Achats** activé dans la Sidebar.
- Trois onglets : **Demandes d'achat**, **Bons de commande**, **Réceptions**.
- Formulaires multi-lignes avec produits, quantités et prix.
- Workflow visuel : brouillon → soumise → convertie ; commande → réception partielle → réceptionnée.
- Formulaire de réception permettant de saisir les quantités réellement reçues.
- Recherche des documents et affichage des statuts.

## RBAC

Le module réutilise les permissions déjà prévues dans `008_roles_permissions_preconfigures.sql` :

- `achats.consulter`
- `achats.creer`
- `achats.modifier`
- `achats.valider`
- `achats.exporter`

Le profil **Responsable Achats** dispose des droits métier nécessaires selon le modèle RBAC existant.

## Base existante : étape obligatoire

Les nouvelles entreprises recevront automatiquement la migration via `provisioning.py`.

Pour les entreprises déjà créées, exécuter depuis `backend` :

```bash
python -m app.scripts.migrate_achats
```

Le script parcourt les `nom_base` enregistrés dans la base centrale et applique la migration à chaque tenant.

## Lancer ensuite

Backend :

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend :

```bash
npm install
npm run dev
```

Puis ouvrir **Achats** dans le menu latéral.

## Pré-requis métier

La création d'une demande ou d'un bon de commande utilise les tables `produit` et `fournisseur`. Il faut donc disposer d'au moins un produit et un fournisseur dans la base entreprise.
# Évolution du projet ERP — Ventes + Achats

Le projet fourni contient maintenant deux modules métier opérationnels côté code :

- **Ventes** : Devis → Commande client → Bon de livraison → Facture.
- **Achats** : Demande d'achat → Bon de commande fournisseur → Réception.

Les deux modules utilisent le routage multi-tenant existant et le contrôle d'accès RBAC par module/action.

## Migrations

- `011_ventes_metier.sql`
- `012_achats_metier.sql`

Les nouvelles entreprises reçoivent automatiquement ces migrations via `app/services/provisioning.py`.

Pour les entreprises existantes :

```bash
cd backend
python -m app.scripts.migrate_ventes
python -m app.scripts.migrate_achats
```

## Pages frontend

- `/ventes`
- `/achats`

La Sidebar expose maintenant directement les deux modules.
# Module métier Ventes

Cette version ajoute une première chaîne commerciale complète :

**Devis → Commande client → Bon de livraison → Facture**

## Ce qui a été ajouté

- Migration tenant `011_ventes_metier.sql` : tables `devis`, `ligne_devis`, `bon_livraison`, `ligne_bon_livraison`, `ligne_facture`, numéros métier et liens entre documents.
- API FastAPI `/api/ventes` avec contrôle RBAC et isolation par base entreprise.
- Écran React `/ventes` accessible depuis la Sidebar.
- Création de devis et commandes multi-lignes, quantités, prix, remises et total automatique.
- Modification des devis tant qu'ils sont brouillon/envoyé.
- Cycle de statut du devis et conversion en commande.
- Création d'un bon de livraison depuis une commande.
- Facturation d'une commande, avec copie immuable des lignes dans la facture.
- Marquage d'une facture comme payée depuis l'interface.
- Compatibilité conservée avec le portail client existant : les factures restent liées à `commande`.

## Base existante : étape obligatoire

Les nouvelles entreprises recevront automatiquement la migration via `provisioning.py`.

Pour les entreprises déjà créées, exécuter depuis `backend` :

```bash
python -m app.scripts.migrate_ventes
```

Le script parcourt les `nom_base` enregistrés dans la base centrale et applique la migration à chaque tenant.

## Lancer ensuite

Backend :

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend :

```bash
npm install
npm run dev
```

Puis ouvrir **Ventes** dans le menu latéral.

## Pré-requis métier

La création d'un devis/commande utilise les tables `client` et `produit`. Il faut donc au moins un client et un produit présents dans la base entreprise. Le module expose `GET /api/ventes/references` pour les charger dans les listes.

## Suite logique du chantier

La base est maintenant prête pour les étapes suivantes : PDF devis/BL/facture, TVA et conditions de paiement, livraison partielle, avoirs, suppression/annulation contrôlée, gestion complète Clients et Produits, export, journal d'audit et tests automatisés.
# Amélioration — validation du formulaire Clients

## Exigence ciblée

Assistance à la saisie, validation des formulaires et cohérence des données, conformément aux exigences générales de BENJEDDOU Technologie Services.

## Comportement ajouté

- Le nom du client est obligatoire, nettoyé des espaces de début/fin et limité à 150 caractères.
- L’adresse e-mail, si elle est renseignée, est vérifiée et limitée à 150 caractères.
- Le téléphone, s’il est renseigné, accepte un format international courant, avec un + initial facultatif, et contrôle les caractères ainsi que le nombre de chiffres (7 à 15).
- L’adresse est nettoyée des espaces superflus et limitée à 1 000 caractères dans ce formulaire.
- Les erreurs sont présentées au niveau du champ concerné, avec attributs d’accessibilité et focus du premier champ invalide.
- Le backend répète les validations : la qualité ne dépend donc pas uniquement du navigateur.
- Les champs facultatifs laissés vides sont normalisés à `null`.

## Fichiers concernés

- `frontend/src/pages/Clients.jsx`
- `frontend/src/validation/client.js` (nouveau)
- `frontend/src/styles/global.css`
- `frontend/tests/clientValidation.test.js` (nouveau)
- `frontend/package.json` (commande `npm test`)
- `backend/app/routers/clients.py`
- `backend/app/schemas/clients.py` (nouveau)
- `backend/app/schemas/__init__.py` (nouveau)
- `backend/tests/test_client_payload.py` (nouveau)

## Vérifications exécutées

- Tests frontend : 6 réussis, 0 échec.
- Tests backend : 7 réussis, 0 échec.
- Compilation syntaxique Python (`py_compile`) : réussie.
- Le build de production Vite n’a pas pu être confirmé dans l’environnement de préparation : le téléchargement des dépendances npm a échoué avec une erreur DNS `EAI_AGAIN`.

## Exécuter les vérifications sur le poste de développement

Dans PowerShell, à la racine du projet :

```powershell
cd frontend
npm ci
npm test
npm run build
```

Puis, avec l’environnement Python du backend activé :

```powershell
cd ..\backend
python -m unittest discover -s tests -v
```

Tester ensuite la création et la modification d’un client dans l’application, avec des données valides et invalides, avant de considérer l’amélioration validée de bout en bout.

## Limites

Cette livraison porte sur le formulaire Clients uniquement. Elle n’implémente pas encore une validation globale pour les autres modules, une recherche globale, la sécurité complète ou le Dashboard analytique.

Le projet distribué ne contient pas le fichier local `.env`, le répertoire `.git`, les dépendances installées (`node_modules`) ni les fichiers temporaires. Conserver le `.env` déjà utilisé sur le poste et ne jamais publier ses valeurs.


## Évolutions du 16 octobre 2026

### 1. Détection des doublons
- Ajout d'une vérification serveur avant l'enregistrement, à partir de l'adresse e-mail et du numéro de téléphone.
- Comparaison des e-mails sans tenir compte des majuscules et comparaison des téléphones à partir des chiffres, afin de repérer des formats d'affichage différents.
- Le backend bloque également la création ou la modification si l'e-mail ou le téléphone est déjà associé à un autre client. La vérification existante du nom est conservée.

### 2. Assistance à la saisie
- Ajout de suggestions de correction pour quelques fautes de domaine e-mail courantes (par exemple `gmal.com` vers `gmail.com`).
- La correction est proposée à l'utilisateur et n'est jamais appliquée automatiquement. Il s'agit d'une assistance heuristique, pas d'un modèle d'IA.

### 3. Fiche détaillée du client
- Ajout d'une action « Fiche » dans la liste des clients.
- La fiche affiche l'identifiant, le nom, l'e-mail, le téléphone, l'adresse et le nombre de commandes associées.
- La fiche propose un accès direct à la modification du client.

### Vérifications réalisées
- Les tests unitaires backend de validation du payload passent (7 tests).
- Les tests frontend de validation et de suggestion sont présents dans `frontend/tests/clientValidation.test.js`.
- Le build Vite n'a pas pu être confirmé dans cet environnement, car l'installation des dépendances npm n'a pas abouti. Un build et des essais fonctionnels dans l'environnement Docker du projet restent nécessaires avant de considérer ces évolutions comme validées en intégration.
