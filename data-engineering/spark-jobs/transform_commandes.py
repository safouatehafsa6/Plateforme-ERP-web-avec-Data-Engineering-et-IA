"""Etape 2 - RAW (JSONL) -> STAGING (Parquet), uniquement pour le run courant."""
import re
import sys
from urllib.parse import urlparse

from pyspark.sql import functions as F

from pipeline_common import build_spark, get_run_id, lake_uri


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.=-]", "_", str(value))


def get_path_metadata(file_path):
    """Extrait entreprise / schema / table du chemin company_<id>/<schema>/<table>/<fichier>."""
    parts = urlparse(file_path).path.strip("/").split("/")
    for index, part in enumerate(parts):
        match = re.fullmatch(r"company_(\d+)", part)
        if match and len(parts) >= index + 4:
            return {
                "company": part,
                "company_id": int(match.group(1)),
                "schema": parts[index + 1],
                "table": parts[index + 2],
                "file": parts[-1],
            }
    raise ValueError(f"Chemin brut inattendu (company_<id>/<schema>/<table>/<fichier>) : {file_path}")


def discover_run_files(spark, root_path, run_id):
    """Fichiers JSONL du run courant uniquement."""
    jvm = spark.sparkContext._jvm
    conf = spark.sparkContext._jsc.hadoopConfiguration()
    root = jvm.org.apache.hadoop.fs.Path(root_path)
    fs = root.getFileSystem(conf)

    suffix = f"_{run_id}.jsonl"
    found, pending = [], [root]
    while pending:
        current = pending.pop()
        for status in fs.listStatus(current):
            path = status.getPath()
            if status.isDirectory():
                pending.append(path)
            elif path.getName().endswith(suffix):
                found.append(path.toString())
    return sorted(found)


def transform_dataframe(df, metadata, run_id):
    for column_name, data_type in df.dtypes:
        if data_type == "string":
            df = df.withColumn(column_name, F.trim(F.col(column_name)))
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
    run_id = get_run_id()
    raw_root = lake_uri("raw")
    staging_root = lake_uri("staging")

    spark = build_spark("ERP-JSONL-to-Parquet")
    errors, transformed, skipped, total_rows = [], 0, 0, 0

    try:
        files = discover_run_files(spark, raw_root, run_id)
        print(f"Run {run_id} : {len(files)} fichier(s) JSONL a transformer")
        if not files:
            raise RuntimeError(f"Aucun fichier brut trouve pour le run {run_id}.")

        jvm = spark.sparkContext._jvm
        conf = spark.sparkContext._jsc.hadoopConfiguration()

        for source_path in files:
            try:
                source = jvm.org.apache.hadoop.fs.Path(source_path)
                if source.getFileSystem(conf).getFileStatus(source).getLen() == 0:
                    skipped += 1
                    print(f"[VIDE] {source_path}")
                    continue

                metadata = get_path_metadata(source_path)
                df = (
                    spark.read.option("mode", "FAILFAST")
                    .option("multiLine", "false")
                    .json(source_path)
                )
                if not df.columns:
                    raise ValueError("Aucune colonne detectee dans un fichier non vide")

                row_count = df.count()
                if row_count == 0:
                    skipped += 1
                    print(f"[SANS DONNEES] {source_path}")
                    continue

                df = transform_dataframe(df, metadata, run_id)
                base_name = metadata["file"].removesuffix(".jsonl")
                output_path = (
                    f"{staging_root}/{safe_name(metadata['company'])}/"
                    f"{safe_name(metadata['schema'])}/{safe_name(metadata['table'])}/"
                    f"{safe_name(base_name)}"
                )
                # Chemin propre au run : l'ecraser ne touche que ce run
                # (permet a Airflow de relancer la tache sans erreur).
                df.write.mode("overwrite").parquet(output_path)

                transformed += 1
                total_rows += row_count
                print(f"[OK] {metadata['company']} / {metadata['table']} : {row_count} lignes")
            except Exception as exc:
                errors.append(f"{source_path}: {type(exc).__name__}: {exc}")
                print(f"[ERREUR] {errors[-1]}", file=sys.stderr)
    finally:
        spark.stop()

    print(
        f"\nResume : fichiers transformes={transformed} | vides={skipped} | "
        f"erreurs={len(errors)} | lignes={total_rows} | run_id={run_id}"
    )
    if errors:
        raise RuntimeError(f"{len(errors)} fichier(s) non transformes :\n- " + "\n- ".join(errors))


if __name__ == "__main__":
    main()
