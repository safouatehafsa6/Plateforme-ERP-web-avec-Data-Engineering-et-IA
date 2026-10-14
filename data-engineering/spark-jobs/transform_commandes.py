
import os
import re
import sys
from urllib.parse import urlparse
from datetime import datetime, timezone

from dotenv import dotenv_values
from pyspark.sql import SparkSession
from pyspark.sql import functions as F


ENV_PATH = "/tmp/erp.env"
RAW_PATH = "s3a://raw/"
STAGING_PATH = "s3a://staging/"


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.=-]", "_", str(value))


def get_path_metadata(file_path):
    parsed = urlparse(file_path)
    parts = parsed.path.strip("/").split("/")

    company = parts[0] if len(parts) >= 1 else "unknown_company"
    schema_name = parts[-3] if len(parts) >= 4 else "unknown_schema"
    table_name = parts[-2] if len(parts) >= 4 else "unknown_table"
    file_name = parts[-1] if parts else "unknown_file"

    match = re.fullmatch(r"company_(\d+)", company)

    return {
        "company": company,
        "company_id": int(match.group(1)) if match else None,
        "schema": schema_name,
        "table": table_name,
        "file": file_name,
    }


def discover_jsonl_files(spark, root_path):
    jvm = spark.sparkContext._jvm
    hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()

    root = jvm.org.apache.hadoop.fs.Path(root_path)
    fs = root.getFileSystem(hadoop_conf)

    discovered = []
    pending = [root]

    while pending:
        current = pending.pop()

        for status in fs.listStatus(current):
            path = status.getPath()

            if status.isDirectory():
                pending.append(path)
            elif path.getName().lower().endswith(".jsonl"):
                discovered.append(path.toString())

    return sorted(discovered)


def transform_dataframe(df, metadata, run_id):
    for column_name, data_type in df.dtypes:
        if data_type == "string":
            df = df.withColumn(
                column_name,
                F.trim(F.col(column_name))
            )

    return (
        df.withColumn("_company_id", F.lit(metadata["company_id"]).cast("integer"))
        .withColumn("_company", F.lit(metadata["company"]))
        .withColumn("_source_schema", F.lit(metadata["schema"]))
        .withColumn("_source_table", F.lit(metadata["table"]))
        .withColumn("_source_file", F.lit(metadata["file"]))
        .withColumn("_run_id", F.lit(run_id))
        .withColumn("_processed_at", F.current_timestamp())
    )


def main():
    config = dotenv_values(ENV_PATH)

    access_key = config.get("MINIO_ROOT_USER")
    secret_key = config.get("MINIO_ROOT_PASSWORD")

    if not access_key or not secret_key:
        raise RuntimeError(
            f"Identifiants MinIO manquants dans {ENV_PATH}"
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    spark = (
        SparkSession.builder
        .appName("ERP-JSONL-to-Parquet")
        .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config(
            "spark.hadoop.fs.s3a.impl",
            "org.apache.hadoop.fs.s3a.S3AFileSystem"
        )
        .config(
            "spark.hadoop.fs.s3a.connection.ssl.enabled",
            "false"
        )
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    discovered = discover_jsonl_files(spark, RAW_PATH)

    print(f"Fichiers JSONL découverts : {len(discovered)}")

    transformed_files = 0
    skipped_empty_files = 0
    failed_files = 0
    total_rows = 0
    errors = []

    jvm = spark.sparkContext._jvm
    hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()

    for source_path in discovered:
        try:
            source = jvm.org.apache.hadoop.fs.Path(source_path)
            fs = source.getFileSystem(hadoop_conf)
            file_size = fs.getFileStatus(source).getLen()

            if file_size == 0:
                skipped_empty_files += 1
                print(f"[VIDE] {source_path}")
                continue

            metadata = get_path_metadata(source_path)

            df = (
                spark.read
                .option("mode", "FAILFAST")
                .option("multiLine", "false")
                .json(source_path)
            )

            if not df.columns:
                raise ValueError(
                    "Aucune colonne détectée dans un fichier non vide"
                )

            row_count = df.count()

            if row_count == 0:
                skipped_empty_files += 1
                print(f"[SANS DONNÉES] {source_path}")
                continue

            df = transform_dataframe(df, metadata, run_id)

            # Chemin distinct par entreprise, schéma, table et fichier.
            base_name = (
                metadata["file"][:-6]
                if metadata["file"].endswith(".jsonl")
                else metadata["file"]
            )

            output_path = (
                f"{STAGING_PATH.rstrip('/')}/"
                f"{safe_name(metadata['company'])}/"
                f"{safe_name(metadata['schema'])}/"
                f"{safe_name(metadata['table'])}/"
                f"{safe_name(base_name)}"
            )

            # Ne pas écraser une sortie existante.
            output = jvm.org.apache.hadoop.fs.Path(output_path)
            output_fs = output.getFileSystem(hadoop_conf)

            if output_fs.exists(output):
                raise FileExistsError(
                    f"Le chemin de sortie existe déjà : {output_path}"
                )

            (
                df.write
                .mode("errorifexists")
                .parquet(output_path)
            )

            transformed_files += 1
            total_rows += row_count

            print(
                f"[OK] {metadata['company']} / "
                f"{metadata['table']} : {row_count} lignes"
            )
            print(f"     Sortie : {output_path}")

        except Exception as exc:
            failed_files += 1
            message = f"{source_path}: {type(exc).__name__}: {exc}"
            errors.append(message)
            print(f"[ERREUR] {message}", file=sys.stderr)

    print("\n========== RÉSUMÉ ==========")
    print(f"Fichiers découverts : {len(discovered)}")
    print(f"Fichiers transformés : {transformed_files}")
    print(f"Fichiers vides ignorés : {skipped_empty_files}")
    print(f"Fichiers en erreur : {failed_files}")
    print(f"Total des lignes écrites : {total_rows}")
    print(f"Run ID : {run_id}")

    spark.stop()

    if failed_files:
        raise RuntimeError(
            f"{failed_files} fichier(s) n'ont pas été transformés. "
            "Consulte les erreurs ci-dessus."
        )


if __name__ == "__main__":
    main()
