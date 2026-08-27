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
