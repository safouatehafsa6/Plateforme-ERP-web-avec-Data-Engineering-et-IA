# Import/export et sécurité des bases de données

## 1. Importation et exportation

Routes authentifiées et réservées au rôle Admin de l'entreprise :

- `GET /api/transferts/formats`
- `GET /api/transferts/export/{table}?format=csv&date_debut=2026-01-01&date_fin=2026-12-31&categorie=...`
- `POST /api/transferts/import/{table}` (multipart `fichier`)

Les tables sont limitées par une liste blanche dans `app/services/transferts.py`. Les identifiants SQL sont construits avec `psycopg2.sql.Identifier`, jamais avec une concaténation libre. L'import est transactionnel, limité à 25 Mo et 10 000 lignes. Il ignore la colonne `id` pour laisser la séquence PostgreSQL générer les identifiants. Une erreur annule la transaction.

### Formats et limites explicites

| Format | Export | Import | Remarque |
|---|---:|---:|---|
| CSV, XLSX, JSON, XML, YAML | Oui | Oui | Formats d'échange structurés |
| SQLite | Oui | Oui | Une seule table de données à l'import |
| DBF | Oui | Oui | Champs exportés en texte ; DBF limite les noms de champs |
| ODS | Oui | Oui | Import/export tabulaire |
| RTF, ODT | Oui | Non | Documents lisibles, pas des formats de réimport tabulaire |
| ZIP, TAR, GZ | Oui | Oui | Une seule archive CSV autorisée, contrôles de taille et de chemin |
| BAK PostgreSQL | Oui, via sauvegarde | Restauration dédiée | Dump natif `pg_dump` chiffré |
| CDX | Non autonome | Non autonome | Index FoxPro/dBASE associé à un DBF. Il faut connaître le moteur cible, les expressions d'index et la structure exacte du DBF pour le générer correctement ; un CDX isolé ne contient pas les données métier. |

Le format `BAK` est ici un fichier de sauvegarde PostgreSQL custom chiffré (`.bak.enc`), et non un export de table. Les archives ne sont pas extraites sur le disque : le CSV est lu en mémoire, avec contrôle du chemin, du nombre de fichiers et de la taille décompressée. La prise en charge de l'import ODS/RTF/ODT/archives et la génération CDX sont des extensions restantes, non annoncées comme validées.

## 2. Argon2id et migration des mots de passe

Les nouveaux mots de passe (création de comptes et réinitialisation) sont hachés avec Argon2id. Lorsqu'un utilisateur se connecte avec un ancien hash bcrypt valide, le backend remplace ce hash par Argon2id après vérification réussie. La migration est progressive et ne nécessite pas de réinitialiser tous les mots de passe. Le hash factice bcrypt demeure utilisé pour le chemin anti-énumération des comptes inconnus.

## 3. Chiffrement et intégrité des sauvegardes

Le module `app/security/crypto.py` fournit :
- AES-256-GCM avec nonce aléatoire de 96 bits et authentification intégrée ;
- HMAC-SHA-256 avec une clé distincte ;
- contrôle en temps constant de la signature.

Les clés ne sont pas écrites dans le code. Le fournisseur local par variables d'environnement est le mode par défaut (`ERP_KEY_PROVIDER=env`). Un adaptateur AWS KMS optionnel est disponible (`ERP_KEY_PROVIDER=aws-kms`, `AWS_REGION`, `AWS_KMS_KEY_ID`) : il utilise `GenerateDataKey` pour chaque sauvegarde et conserve la clé de données chiffrée KMS dans l'enveloppe. L'identité d'exécution doit disposer des droits KMS nécessaires. La clé HMAC reste une clé distincte (`ERP_HMAC_KEY`) à injecter depuis un coffre de secrets. Définir ces valeurs dans un gestionnaire de secrets ou dans l'environnement sécurisé du déploiement. Générer chaque clé indépendamment en mode env :

```bash
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Ne jamais committer ces valeurs. En mode env, sauvegarder les clés dans un coffre externe (KMS/Vault) et mettre en place une procédure de rotation avec conservation des anciennes clés. En mode AWS KMS, conserver la clé KMS et les autorisations de déchiffrement tant que des sauvegardes l'utilisent. Une sauvegarde ne peut pas être déchiffrée si sa clé est perdue ou si l'accès KMS est révoqué.

### Sauvegarde et restauration

- Création : `POST /api/securite/sauvegardes` ; exécute `pg_dump --format=custom`.
- Téléchargement : `GET /api/securite/sauvegardes/{fichier}` ; fournit un paquet ZIP contenant le fichier `.bak.enc` et son fichier `.hmac` associé.
- Vérification : `POST /api/securite/sauvegardes/verifier` ; contrôle HMAC, déchiffrement AES-GCM et lecture de l'en-tête via `pg_restore --list`.
- Restauration : `POST /api/securite/sauvegardes/restaurer` ; exige la confirmation `RESTAURER <nom_de_base>`, puis crée automatiquement une sauvegarde chiffrée de l'état courant avant le `pg_restore --clean`.

Le compte système qui exécute le backend doit pouvoir écrire dans `ERP_BACKUP_DIR`. Protéger ce volume, limiter l'accès aux sauvegardes, les copier hors machine et tester régulièrement une restauration sur une base isolée. La vérification cryptographique ne remplace pas un exercice complet de reprise après sinistre.

Le backend doit contenir les utilitaires PostgreSQL 16 (`pg_dump`, `pg_restore`) ; ils sont ajoutés à l'image via `backend/Dockerfile`.

## 4. TLS PostgreSQL

La connexion psycopg2 accepte `DB_SSLMODE` et `DB_SSLROOTCERT`. En production, utiliser `DB_SSLMODE=verify-full`, une autorité de certification approuvée et un certificat serveur dont le SAN correspond au nom DNS `postgres-erp`. Ne pas utiliser `disable` ou `allow` en production. Le mode `prefer` reste une valeur de compatibilité pour le développement local.

Le chiffrement TLS côté serveur nécessite également d'activer `ssl=on` dans PostgreSQL et de lui fournir certificat et clé privée. Le fichier de configuration TLS d'environnement doit être installé et testé avant de passer `DB_SSLMODE=verify-full`. HTTPS doit en plus être activé au point d'entrée HTTP (reverse proxy avec certificat), indépendamment du TLS PostgreSQL.

## 5. Tests obligatoires avant mise en production

1. Importer un petit CSV valide, vérifier les lignes dans PostgreSQL et tester l'annulation sur une ligne invalide.
2. Exporter une table en CSV/XLSX/JSON/SQLite/DBF et réimporter dans une base de test.
3. Vérifier les filtres de dates et catégorie selon les colonnes présentes.
4. Vérifier qu'un utilisateur non Admin reçoit HTTP 403.
5. Se connecter avec un ancien hash bcrypt et confirmer qu'il devient `$argon2id$`.
6. Vérifier qu'un fichier de sauvegarde modifié échoue au contrôle HMAC.
7. Restaurer une sauvegarde dans une base isolée et comparer les volumes de lignes.
8. Vérifier TLS avec `verify-full` depuis le backend et confirmer que l'absence d'une CA valide fait échouer la connexion.

### Activation TLS dans Docker (environnement de test)

Depuis la racine du dépôt, sur Linux/VMware avec OpenSSL :

```bash
bash deploy/generer_certificats_postgres.sh
# Définir DB_SSLMODE=verify-full et DB_SSLROOTCERT=/run/postgres-tls/ca.crt dans l'environnement backend (déjà fournis par l'overlay)
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
docker compose logs postgres-erp backend
```

Le certificat généré est une CA locale de test. En production, le remplacer par un certificat signé par la PKI de l'entreprise. Ne jamais committer `secrets/postgres/`, en particulier `ca.key` et `server.key`.
