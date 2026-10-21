# Procédure de test – import de documents RAG (PowerShell / Docker Compose)

## 0. Mise en place (une seule fois)
```powershell
# Reconstruire le backend (FastEmbed et modèle d'embeddings local)
docker compose build backend frontend
docker compose up -d

# Appliquer les migrations aux bases entreprise DÉJÀ créées (les nouvelles les reçoivent via le provisioning)
$bases = docker compose exec -T postgres-erp psql -U erp_user -d erp_db -Atc "SELECT DISTINCT nom_base FROM compte_index"
foreach ($db in $bases) {
  foreach ($f in "013_assistant_rag","014_assistant_documents","015_documents_permissions","016_assistant_rag_embeddings") {
    Get-Content "backend\database\tenant-template\$f.sql" -Raw | docker compose exec -T postgres-erp psql -U erp_user -d $db -q
  }
  Write-Host "OK $db"
}
```
Attendu : aucune ligne `ERROR`. Les scripts sont idempotents. Le bucket `rag-documents` est créé par `minio-init` ou, à défaut, automatiquement par le backend au premier import.
> Les rôles autres qu'Admin n'ont pas `documents.*` : l'Admin les attribue dans **Rôles & Permissions** (module `documents`).

## 1. Connexion (Swagger : http://localhost:8000/docs)
1. `POST /api/auth/login` avec e-mail + mot de passe (le CAPTCHA n'est exigé qu'après 2 échecs ; s'il l'est : `GET /api/auth/captcha`, lire le code avec `docker compose logs backend --tail 20 | Select-String Captcha`, puis le renvoyer immédiatement avec `captchaId` et `captchaValeur`).
2. Copier le champ `token`, cliquer sur **Authorize**, coller le token **sans** « Bearer ».
Échec `Not authenticated` = pas de token ; `Jeton invalide` = token tronqué ; `Session expirée` = se reconnecter.

## 2. Tests (depuis l'ERP : icône trombone dans l'assistant, ou Swagger)
| # | Test | Résultat attendu | Diagnostic si échec |
|---|------|------------------|---------------------|
| 1 | Import PDF texte | 201 + `nbChunks` > 0 | 500 → `docker compose logs backend --tail 50` |
| 2 | Import DOCX | 201 | idem |
| 3 | Original dans MinIO | objet `<entrepriseId>/<uuid>.pdf` dans `rag-documents` (console http://localhost:9001) | 503 → variables `MINIO_*`, service `minio` |
| 4 | Chunks en base | voir requête ci-dessous | table absente → migrations 013/014 non appliquées à cette base |
| 5 | Question exprimée avec des mots différents de ceux du document | passage sémantiquement pertinent + Sources (fichier + page) | vérifier le cache modèle, les logs et la permission `documents.consulter` |
| 6 | Utilisateur sans `documents.creer` | 403 `Permission requise : documents.creer.` | — |
| 7 | Autre entreprise | liste vide, aucune source | — |
| 8 | Fichier > 10 Mo / `.exe` / faux PDF / PDF scanné | 413 / 422 / 422 / 422 (mention OCR) | — |
| 9 | Non-régression | « Synthèse des ventes », création client/commande fonctionnent | — |

```powershell
# Test 4
docker compose exec -T postgres-erp psql -U erp_user -d <nom_base> -c "SELECT d.titre, d.nb_chunks, count(c.id) AS chunks FROM assistant_document d LEFT JOIN assistant_document_chunk c ON c.document_id=d.id GROUP BY 1,2"
# Test 3 (liste des objets depuis le backend)
docker compose exec -T backend python -c "from app.services import rag_documents as r; print([o.object_name for o in r._client().list_objects(r.BUCKET_RAG, recursive=True)])"
# Import en ligne de commande
curl.exe -X POST http://localhost:8000/api/assistant/documents/upload -H "Authorization: Bearer $token" -F "fichier=@C:\chemin\Cours.pdf" -F "titre=Cours virtualisation"
```

## 3. Test automatisé (sans Docker, avec PostgreSQL + MinIO simulé)
`backend/tests/e2e_rag_manual.py` rejoue les cas 1–13 sur deux bases entreprise (variables en tête du fichier).

## Limites
- Pas d'OCR : un PDF scanné est refusé avec un message explicite.
- Le modèle d'embeddings se télécharge au premier lancement si le cache Docker est vide; le premier import peut donc prendre plus de temps.
- La recherche sémantique est locale, mais le composant retourne les passages trouvés plutôt que de générer une synthèse LLM.
