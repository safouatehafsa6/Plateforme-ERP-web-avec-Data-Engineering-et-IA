"""Configuration commune aux jobs du pipeline ERP.

Regle : aucune valeur sensible n'est ecrite dans le code, et aucun fichier
.env n'est copie dans /tmp. Tout vient des variables d'environnement du
conteneur Airflow (definies dans docker-compose.yml a partir du .env).
"""
import os
import re

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
IDENT_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


def require_env(*names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Variables d'environnement manquantes : " + ", ".join(missing)
        )
    return {name: os.environ[name] for name in names}


def get_run_id():
    """Identifiant unique de l'execution. Il isole les donnees de chaque run
    (un run ne lit jamais les fichiers d'un run precedent)."""
    run_id = os.environ.get("PIPELINE_RUN_ID", "")
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise RuntimeError(
            "PIPELINE_RUN_ID absent ou invalide "
            "(attendu : 8 a 64 caracteres parmi A-Z a-z 0-9 _ -)."
        )
    return run_id


def lake_uri(zone):
    """URI d'une zone du data lake (raw, staging, curated)."""
    return os.environ.get(f"LAKE_{zone.upper()}_URI", f"s3a://{zone}").rstrip("/")


def minio_settings():
    creds = require_env("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD")
    return {
        "endpoint": os.environ.get("MINIO_ENDPOINT", "minio:9000"),
        "access_key": creds["MINIO_ROOT_USER"],
        "secret_key": creds["MINIO_ROOT_PASSWORD"],
    }


def db_settings():
    creds = require_env("ERP_DB_USER", "ERP_DB_PASSWORD")
    return {
        "host": os.environ.get("ERP_DB_HOST", "postgres-erp"),
        "port": int(os.environ.get("ERP_DB_PORT", "5432")),
        "user": creds["ERP_DB_USER"],
        "password": creds["ERP_DB_PASSWORD"],
        "central_db": os.environ.get("ERP_DB_NAME", "erp_db"),
    }


def build_spark(app_name):
    from pyspark.sql import SparkSession

    minio = minio_settings()
    spark = (
        SparkSession.builder.appName(app_name)
        .config("spark.hadoop.fs.s3a.endpoint", f"http://{minio['endpoint']}")
        .config("spark.hadoop.fs.s3a.access.key", minio["access_key"])
        .config("spark.hadoop.fs.s3a.secret.key", minio["secret_key"])
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def write_text(spark, path, text):
    """Ecrit un petit fichier texte (JSON) dans le data lake via l'API Hadoop."""
    jvm = spark.sparkContext._jvm
    conf = spark.sparkContext._jsc.hadoopConfiguration()
    target = jvm.org.apache.hadoop.fs.Path(path)
    fs = target.getFileSystem(conf)
    stream = fs.create(target, True)
    try:
        stream.write(bytearray(text.encode("utf-8")))
    finally:
        stream.close()
