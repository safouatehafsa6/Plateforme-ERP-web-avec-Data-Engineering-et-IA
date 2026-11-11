"""Applique Room Live (salles persistantes + enregistrements) à la base centrale ET à toutes les
bases entreprise existantes, en une seule commande.

Script idempotent (CREATE ... IF NOT EXISTS), sans suppression de données : relançable sans risque.
(Le backend applique aussi ce schéma automatiquement, base par base, à la première utilisation ;
cette commande sert à le faire explicitement, par exemple avant une mise en production.)

Usage depuis le dossier backend :
    python -m app.scripts.migrate_room_live
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
DOSSIER = Path(__file__).resolve().parents[2] / "database"
SCRIPT_TENANT = DOSSIER / "tenant-template" / "021_room_live.sql"
SCRIPT_CENTRAL = DOSSIER / "central" / "016_room_live.sql"


def connexion(dbname):
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=dbname)


def appliquer(dbname: str, script: Path) -> None:
    conn = connexion(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(script.read_text(encoding="utf-8"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    echecs = []
    cibles = [(DB_CENTRAL_NAME, SCRIPT_CENTRAL)]
    central = connexion(DB_CENTRAL_NAME)
    try:
        with central.cursor() as cur:
            cur.execute("SELECT nom_base FROM entreprise WHERE nom_base IS NOT NULL ORDER BY id")
            cibles += [(r[0], SCRIPT_TENANT) for r in cur.fetchall()]
    finally:
        central.close()
    for nom_base, script in cibles:
        try:
            appliquer(nom_base, script)
            print(f"[OK] {nom_base}")
        except Exception as exc:
            echecs.append((nom_base, str(exc)))
            print(f"[ERREUR] {nom_base}: {exc}")
    if echecs:
        raise SystemExit(f"Migration terminée avec {len(echecs)} échec(s).")
    print(f"Room Live appliqué à {len(cibles)} base(s) (centrale + entreprises).")


if __name__ == "__main__":
    main()
