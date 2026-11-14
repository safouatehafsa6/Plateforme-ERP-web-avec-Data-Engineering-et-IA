"""Migration des tables RAG vers les bases des entreprises."""

import os
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "postgres-erp")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "erp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "erp_password")
DB_CENTRAL_NAME = os.getenv("DB_CENTRAL_NAME", "erp_db")

TEMPLATE = Path(__file__).resolve().parents[2] / "database" / "tenant-template"
SCRIPTS = [
    TEMPLATE / "013_assistant_rag.sql",
    TEMPLATE / "014_assistant_documents.sql",
    TEMPLATE / "016_assistant_rag_embeddings.sql",
]

def connect(dbname):
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=dbname
    )

def main():
    for path in SCRIPTS:
        if not path.is_file():
            raise FileNotFoundError(f"Migration introuvable : {path}")

    with connect(DB_CENTRAL_NAME) as central:
        with central.cursor() as cur:
            cur.execute(
                "SELECT nom_base FROM entreprise "
                "WHERE nom_base IS NOT NULL ORDER BY id"
            )
            databases = [row[0] for row in cur.fetchall()]

    for database in databases:
        try:
            with connect(database) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('public.utilisateur')")
                    if cur.fetchone()[0] is None:
                        print(f"[IGNOREE] {database}: table utilisateur absente")
                        continue

                    for path in SCRIPTS:
                        cur.execute(path.read_text(encoding="utf-8"))
                        print(f"[OK] {database}: {path.name}")

            print(f"[TERMINEE] {database}")
        except Exception as exc:
            print(f"[ERREUR] {database}: {exc}")

if __name__ == "__main__":
    main()
