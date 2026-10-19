"""Etape 1 - Extraction PostgreSQL (une base par entreprise) vers MinIO/raw.

- La liste des entreprises vient de la base centrale (entreprise.statut = 'actif'),
  plus de liste codee en dur.
- Seules les tables listees dans PIPELINE_TABLES sont extraites
  (par defaut : commande) : minimisation des donnees.
- Les colonnes sensibles (mots de passe, jetons, codes de verification...)
  ne sont jamais exportees.
- Connexions en lecture seule. Les fichiers portent le run_id : un run ne
  touche jamais aux fichiers d'un autre run.
"""
import base64
import json
import os
import re
import tempfile
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

import psycopg2
from minio import Minio
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from pipeline_common import IDENT_PATTERN, db_settings, get_run_id, minio_settings

BUCKET = "raw"
SCHEMA = "public"
BATCH_SIZE = 1000

TABLES = [
    name.strip()
    for name in os.environ.get("PIPELINE_TABLES", "commande").split(",")
    if name.strip()
]

SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(^|_)(password|passwd|mot_de_passe|motdepasse|secret|token|api_key|"
    r"private_key|code_verification|verification_code|reset_token|hash|otp)(_|$)",
    re.IGNORECASE,
)


def json_default(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    raise TypeError(f"Type non supporte : {type(value).__name__}")


def connect(dbname):
    cfg = db_settings()
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=dbname,
        user=cfg["user"],
        password=cfg["password"],
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )


def list_companies():
    """Entreprises actives (donc dont la base a ete provisionnee)."""
    only_ids = {
        int(value)
        for value in os.environ.get("PIPELINE_COMPANY_IDS", "").split(",")
        if value.strip()
    }
    conn = connect(db_settings()["central_db"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nom_base FROM entreprise "
                "WHERE statut = 'actif' ORDER BY id"
            )
            companies = [
                {"company_id": row[0], "database": row[1]} for row in cur.fetchall()
            ]
    finally:
        conn.close()

    if only_ids:
        companies = [c for c in companies if c["company_id"] in only_ids]
    return companies


def table_exists(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s AND table_type = 'BASE TABLE'",
            (SCHEMA, table),
        )
        return cur.fetchone() is not None


def exportable_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
            (SCHEMA, table),
        )
        columns = [row[0] for row in cur.fetchall()]
    included = [c for c in columns if not SENSITIVE_COLUMN_PATTERN.search(c)]
    excluded = [c for c in columns if SENSITIVE_COLUMN_PATTERN.search(c)]
    return included, excluded


def extract_table(conn, minio_client, company, table, run_id):
    columns, excluded = exportable_columns(conn, table)
    if excluded:
        print(f"  Colonnes sensibles exclues : {excluded}")
    if not columns:
        raise RuntimeError(f"{SCHEMA}.{table} : aucune colonne exportable")

    query = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        sql.Identifier(SCHEMA, table),
    )

    object_name = (
        f"company_{company['company_id']}/{SCHEMA}/{table}/{table}_{run_id}.jsonl"
    )

    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as out:
        row_count = 0
        with conn.cursor(name="extract_cursor", cursor_factory=RealDictCursor) as cur:
            cur.itersize = BATCH_SIZE
            cur.execute(query)
            for row in cur:
                record = dict(row)
                record["_source"] = {
                    "company_id": company["company_id"],
                    "schema": SCHEMA,
                    "table": table,
                }
                line = json.dumps(record, default=json_default, ensure_ascii=False)
                out.write((line + "\n").encode("utf-8"))
                row_count += 1

        size = out.tell()
        out.seek(0)
        minio_client.put_object(
            BUCKET,
            object_name,
            data=out,
            length=size,
            content_type="application/x-ndjson",
            part_size=10 * 1024 * 1024,
        )

    print(f"  OK | {SCHEMA}.{table} | lignes={row_count} | octets={size}")
    return row_count


def main():
    run_id = get_run_id()

    for table in TABLES:
        if not IDENT_PATTERN.fullmatch(table):
            raise RuntimeError(f"Nom de table invalide dans PIPELINE_TABLES : {table!r}")
    if not TABLES:
        raise RuntimeError("PIPELINE_TABLES est vide.")

    minio_cfg = minio_settings()
    minio_client = Minio(
        minio_cfg["endpoint"],
        access_key=minio_cfg["access_key"],
        secret_key=minio_cfg["secret_key"],
        secure=False,
    )
    if not minio_client.bucket_exists(BUCKET):
        raise RuntimeError(f"Le bucket MinIO '{BUCKET}' n'existe pas")

    companies = list_companies()
    if not companies:
        raise RuntimeError("Aucune entreprise active trouvee : extraction impossible.")

    print(f"Run {run_id} | tables : {TABLES} | entreprises actives : {len(companies)}")

    errors = []
    total_rows = 0

    for company in companies:
        print(f"\nEntreprise {company['company_id']}")
        conn = None
        try:
            conn = connect(company["database"])
            for table in TABLES:
                try:
                    if not table_exists(conn, table):
                        raise RuntimeError(f"table {SCHEMA}.{table} introuvable")
                    total_rows += extract_table(conn, minio_client, company, table, run_id)
                except Exception as exc:
                    errors.append(f"entreprise {company['company_id']} | {table} | {exc}")
                    print(f"  ERREUR : {errors[-1]}")
                    conn.rollback()
        except Exception as exc:
            errors.append(f"entreprise {company['company_id']} | connexion | {exc}")
            print(f"  ERREUR : {errors[-1]}")
        finally:
            if conn is not None:
                conn.close()

    print(f"\nResume : lignes={total_rows} | erreurs={len(errors)} | run_id={run_id}")
    if errors:
        raise RuntimeError("Extraction incomplete :\n- " + "\n- ".join(errors))
    print("Extraction terminee avec succes.")


if __name__ == "__main__":
    main()
