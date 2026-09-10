import os
import psycopg2

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "erp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "erp_password")

# Chemin du script SQL qui définit le schéma type d'une entreprise
# (utilisateurs, rôles, clients, produits, commandes...).
CHEMIN_SCHEMA_ENTREPRISE = os.path.join(
    os.path.dirname(__file__), "..", "..", "database", "tenant-template", "001_init_schema_entreprise.sql"
)


def _connexion_maintenance():
    """Connexion à la base 'postgres' (toujours présente), nécessaire pour
    exécuter un CREATE DATABASE, qui ne peut pas se faire à l'intérieur
    d'une transaction normale."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname="postgres"
    )
    conn.autocommit = True
    return conn


def creer_base_entreprise(nom_base: str) -> None:
    """Étape 1 du provisioning : créer une base de données physiquement
    isolée pour cette entreprise (conforme à l'architecture multi-tenant
    du cahier des charges)."""
    conn = _connexion_maintenance()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{nom_base}"')
    finally:
        conn.close()


def initialiser_schema_entreprise(nom_base: str) -> None:
    """Étape 2 : exécuter le script SQL qui crée toutes les tables
    (utilisateur, rôle, client, produit, commande...) dans cette nouvelle
    base, à partir du même script utilisé en développement."""
    with open(CHEMIN_SCHEMA_ENTREPRISE, "r", encoding="utf-8") as f:
        script_sql = f.read()

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=nom_base
    )
    try:
        with conn.cursor() as cur:
            cur.execute(script_sql)
        conn.commit()
    finally:
        conn.close()


def creer_administrateur_entreprise(nom_base: str, nom: str, email: str, mot_de_passe_hash: str) -> None:
    """Étape 3 : créer le rôle Admin et le premier compte utilisateur
    (l'administrateur de l'entreprise) dans sa nouvelle base."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=nom_base
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO role (nom, description) VALUES ('Admin', 'Administrateur de l''entreprise') RETURNING id"
            )
            role_id = cur.fetchone()[0]

            prenom, _, nom_famille = nom.partition(" ")
            cur.execute(
                """INSERT INTO utilisateur (nom, prenom, email, mot_de_passe, role_id)
                   VALUES (%s, %s, %s, %s, %s)""",
                (nom_famille or nom, prenom, email, mot_de_passe_hash, role_id),
            )
        conn.commit()
    finally:
        conn.close()


def provisionner_entreprise(nom_base: str, nom_admin: str, email_admin: str, mot_de_passe_hash: str) -> None:
    """Orchestre les 3 étapes du provisioning, dans l'ordre. Si une étape
    échoue, l'exception remonte pour que l'appelant puisse marquer
    l'entreprise en erreur plutôt que 'active' à tort."""
    creer_base_entreprise(nom_base)
    initialiser_schema_entreprise(nom_base)
    creer_administrateur_entreprise(nom_base, nom_admin, email_admin, mot_de_passe_hash)
