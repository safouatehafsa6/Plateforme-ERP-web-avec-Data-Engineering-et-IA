"""Applique 011_ventes_metier.sql à toutes les bases entreprise connues.

Usage depuis le dossier backend :
    python -m app.scripts.migrate_ventes
"""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "erp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "erp_password")
DB_CENTRAL_NAME = os.getenv("DB_CENTRAL_NAME", "erp_db")
SCRIPT = Path(__file__).resolve().parents[2] / "database" / "tenant-template" / "011_ventes_metier.sql"


def connexion(dbname):
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=dbname)


def main():
    central = connexion(DB_CENTRAL_NAME)
    try:
        with central.cursor() as cur:
            cur.execute("SELECT nom_base FROM entreprise WHERE nom_base IS NOT NULL ORDER BY id")
            bases = [r[0] for r in cur.fetchall()]
    finally:
        central.close()

    sql = SCRIPT.read_text(encoding="utf-8")
    if not bases:
        print("Aucune base entreprise trouvée.")
        return

    echecs = []
    for nom_base in bases:
        conn = None
        try:
            conn = connexion(nom_base)
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"[OK] {nom_base}")
        except Exception as exc:
            if conn:
                conn.rollback()
            echecs.append((nom_base, str(exc)))
            print(f"[ERREUR] {nom_base}: {exc}")
        finally:
            if conn:
                conn.close()

    if echecs:
        raise SystemExit(f"Migration terminée avec {len(echecs)} échec(s).")
    print(f"Migration Ventes appliquée à {len(bases)} base(s) entreprise.")


if __name__ == "__main__":
    main()
