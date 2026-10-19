# Pipeline Data Engineering (etape 1 + 2)

DAG Airflow `erp_data_engineering_pipeline` :

    extract_raw -> transform_staging -> build_curated -> quality_gate

| Tache | Script | Resultat |
|---|---|---|
| extract_raw | extract_commandes_to_minio.py | `raw/company_<id>/public/<table>/<table>_<run_id>.jsonl` |
| transform_staging | transform_commandes.py | `staging/company_<id>/public/<table>/<table>_<run_id>/` (Parquet) |
| build_curated | build_curated_commandes.py | `curated/commandes/run_id=<run_id>/_company_id=<n>/` |
| quality_gate | quality_checks_curated.py | rapport `curated/_meta/quality/<run_id>.json` + pointeur `curated/_meta/latest_success.json` si tout passe |

## Regles
- Tout est configure par variables d'environnement du conteneur Airflow (voir `docker-compose.yml`, service `airflow-scheduler`). Plus de `/tmp/erp.env`, plus d'identifiants ou de nom de base en dur.
- Entreprises : lues dans la base centrale (`entreprise.statut = 'actif'`).
- Tables extraites : `PIPELINE_TABLES` (defaut : `commande`). Colonnes sensibles toujours exclues.
- Un run = un `PIPELINE_RUN_ID` : il ne lit jamais les fichiers d'un autre run.
- Le Dashboard lit UNIQUEMENT le dossier designe par `latest_success.json`.
- Seuils qualite : `QUALITY_MAX_REJECT_PCT` (defaut 5), `QUALITY_MAX_MONTANT` (defaut 1e9).

## Non utilises par le DAG
`etl_erp.py` (base codee en dur + identifiants en clair), `load_curated_commandes_to_postgres.py`
(depend d'une base `erp_analytics` absente du projet), `test_*.py`, `inspect_curated_commandes.py`.

## Bouton Dashboard (etape 3-5)
Flux : bouton **Dashboard** (menu, Administrateur d'entreprise) -> `POST /api/pipeline/run` (FastAPI)
-> DAG Airflow -> `GET /api/pipeline/status/{run_id}` (sondage toutes les 3 s)
-> `POST /api/pipeline/dashboard-token` -> Streamlit (iframe).

- Les donnees de moins de `PIPELINE_MAX_AGE_MINUTES` (defaut 60) sont reutilisees ; **Actualiser** force un nouveau run.
- Jamais deux runs en parallele : si un run est actif, le clic s'y rattache.
- Streamlit exige un jeton signe (5 min) par `DASHBOARD_TOKEN_SECRET` (different de `JWT_SECRET`) et ne charge que la partition `_company_id=<entreprise du jeton>`.
- Generer le secret (PowerShell) :
  `Add-Content .env "DASHBOARD_TOKEN_SECRET=$([guid]::NewGuid().ToString('N'))$([guid]::NewGuid().ToString('N'))"`
