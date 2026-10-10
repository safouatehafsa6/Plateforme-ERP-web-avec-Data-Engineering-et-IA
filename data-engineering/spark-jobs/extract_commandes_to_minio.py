
import json
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import dotenv_values
from minio import Minio


ROOT = Path(__file__).resolve().parents[2]
config = dotenv_values(ROOT / ".env")

COMPANIES = [
    {"company_id": 3, "database": "compte_societe_test_ec11a6c3"},
    {"company_id": 4, "database": "compte_benjjedou_2061bc82"},
    {"company_id": 5, "database": "compte_demo_qr_897caff5"},
]

minio_client = Minio(
    "localhost:9000",
    access_key=config["MINIO_ROOT_USER"],
    secret_key=config["MINIO_ROOT_PASSWORD"],
    secure=False,
)


def json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported type: {type(value).__name__}")


def extract_commandes(company):
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname=company["database"],
        user=config["ERP_DB_USER"],
        password=config["ERP_DB_PASSWORD"],
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, client_id, date_commande, statut,
                       montant_total, numero, devis_id, notes,
                       date_modification
                FROM public.commande
                ORDER BY id
            """)
            rows = cursor.fetchall()

        return [
            {**dict(row), "company_id": company["company_id"]}
            for row in rows
        ]
    finally:
        conn.close()


def main():
    bucket = "raw"

    if not minio_client.bucket_exists(bucket):
        raise RuntimeError(f"Bucket '{bucket}' does not exist")

    all_records = []

    for company in COMPANIES:
        records = extract_commandes(company)
        all_records.extend(records)
        print(
            f"company_id={company['company_id']} | "
            f"database={company['database']} | "
            f"rows={len(records)}"
        )

    content = "".join(
        json.dumps(row, default=json_default, ensure_ascii=False) + "\n"
        for row in all_records
    ).encode("utf-8")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    object_name = f"commandes/commandes_{timestamp}.jsonl"

    minio_client.put_object(
        bucket,
        object_name,
        BytesIO(content),
        len(content),
        content_type="application/x-ndjson",
    )

    print(f"Total extracted: {len(all_records)}")
    print(f"Uploaded: {bucket}/{object_name}")
    print("Extraction completed successfully.")


if __name__ == "__main__":
    main()
