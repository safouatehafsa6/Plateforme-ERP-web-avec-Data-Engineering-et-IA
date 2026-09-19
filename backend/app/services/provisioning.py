import os
import psycopg2

from app.db import pool_central

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "erp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "erp_password")

# Chemin du script SQL qui définit le schéma type d'une entreprise
# (utilisateurs, rôles, clients, produits, commandes...).
DOSSIER_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "..", "database", "tenant-template")

# Scripts de STRUCTURE (tables), appliqués dans cet ordre à l'initialisation.
SCRIPTS_SCHEMA_ENTREPRISE = [
    os.path.join(DOSSIER_TEMPLATE, "001_init_schema_entreprise.sql"),
    os.path.join(DOSSIER_TEMPLATE, "009_utilisateurs_externes.sql"),
]

# Scripts appliqués APRÈS la création du schéma, dans cet ordre. Ils
# préparent le moteur RBAC de la nouvelle entreprise : sans eux, la base
# ne contient aucune permission ni aucun profil métier, et la page
# « Rôles & Permissions » s'affiche vide.
SCRIPTS_SEED_ENTREPRISE = [
    os.path.join(DOSSIER_TEMPLATE, "008_roles_permissions_preconfigures.sql"),
]


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
    """Étape 2 : exécuter les scripts SQL qui créent toutes les tables
    (utilisateur, rôle, client, produit, commande, utilisateur_externe...)
    dans cette nouvelle base, à partir des mêmes scripts utilisés en
    développement."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=nom_base
    )
    try:
        with conn.cursor() as cur:
            for chemin in SCRIPTS_SCHEMA_ENTREPRISE:
                with open(chemin, "r", encoding="utf-8") as f:
                    cur.execute(f.read())
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


def appliquer_seed_rbac(nom_base: str) -> None:
    """Étape 4 : préconfigurer les profils métier et leurs permissions
    (008_roles_permissions_preconfigures.sql).

    Exécuté APRÈS la création du rôle Admin, car le script attribue aussi
    à ce rôle l'intégralité des permissions existantes. Les scripts sont
    idempotents (INSERT ... WHERE NOT EXISTS) : les rejouer ne crée pas
    de doublons."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=nom_base
    )
    try:
        with conn.cursor() as cur:
            for chemin in SCRIPTS_SEED_ENTREPRISE:
                with open(chemin, "r", encoding="utf-8") as f:
                    cur.execute(f.read())
        conn.commit()
    finally:
        conn.close()


def indexer_compte_central(email: str, entreprise_id: int, nom_base: str, type_compte: str = "interne") -> None:
    """Enregistre (ou met à jour) dans la base centrale la correspondance
    email -> entreprise, indispensable au point d'entrée unique de
    connexion : à la saisie de son email, le backend doit pouvoir
    retrouver dans QUELLE base entreprise chercher le compte, sans que
    l'utilisateur ait à le préciser lui-même (voir diagramme de séquence
    'Routage multi-tenant'). N'indexe jamais le mot de passe — celui-ci
    reste uniquement dans la base entreprise elle-même.

    type_compte distingue un compte interne (Admin/collaborateur, table
    utilisateur) d'un compte externe (client/partenaire du portail, table
    utilisateur_externe) : le login lit cette valeur pour savoir dans
    quelle table chercher, sans avoir à interroger les deux à chaque
    tentative de connexion."""
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO compte_index (email, entreprise_id, nom_base, type_compte)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE
                    SET entreprise_id = EXCLUDED.entreprise_id,
                        nom_base = EXCLUDED.nom_base,
                        type_compte = EXCLUDED.type_compte
                """,
                (email.strip().lower(), entreprise_id, nom_base, type_compte),
            )
        conn.commit()
    finally:
        pool_central.putconn(conn)


def provisionner_entreprise(nom_base: str, nom_admin: str, email_admin: str, mot_de_passe_hash: str, entreprise_id: int) -> None:
    """Orchestre les étapes du provisioning, dans l'ordre. Si une étape
    échoue, l'exception remonte pour que l'appelant puisse marquer
    l'entreprise en erreur plutôt que 'active' à tort."""
    creer_base_entreprise(nom_base)
    initialiser_schema_entreprise(nom_base)
    creer_administrateur_entreprise(nom_base, nom_admin, email_admin, mot_de_passe_hash)
    appliquer_seed_rbac(nom_base)
    indexer_compte_central(email_admin, entreprise_id, nom_base)
