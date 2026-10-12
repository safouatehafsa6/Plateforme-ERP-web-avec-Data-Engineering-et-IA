
from dotenv import dotenv_values
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    trim,
    current_timestamp,
    regexp_replace
)
from pyspark.sql.types import DecimalType

ENV_PATH = "/tmp/erp.env"

SOURCE_PATH = "s3a://staging/company_*/public/commande/*"
TARGET_PATH = "s3a://curated/commandes"

config = dotenv_values(ENV_PATH)

spark = (
    SparkSession.builder
    .appName("ERP-Commandes-Curated")
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000")
    .config(
        "spark.hadoop.fs.s3a.access.key",
        config["MINIO_ROOT_USER"]
    )
    .config(
        "spark.hadoop.fs.s3a.secret.key",
        config["MINIO_ROOT_PASSWORD"]
    )
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config(
        "spark.hadoop.fs.s3a.impl",
        "org.apache.hadoop.fs.s3a.S3AFileSystem"
    )
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("ERROR")

try:
    print("=" * 60)
    print("ETAPE 1 - Lecture des commandes depuis Staging")

    df = spark.read.parquet(SOURCE_PATH)

    print("Schema source :")
    df.printSchema()

    print("Nombre de lignes source :", df.count())

    # Nettoyage des champs texte
    df_clean = df

    for field in ["numero", "statut"]:
        if field in df_clean.columns:
            df_clean = df_clean.withColumn(
                field,
                trim(col(field))
            )

    # Conversion du montant en type numérique
    df_clean = df_clean.withColumn(
        "montant_total",
        regexp_replace(
            trim(col("montant_total").cast("string")),
            ",",
            "."
        ).cast(DecimalType(18, 2))
    )

    print("=" * 60)
    print("ETAPE 2 - Validation des données")

    df_valid = df_clean.filter(
        col("id").isNotNull()
        & col("_company_id").isNotNull()
        & (col("_company_id") > 0)
        & col("montant_total").isNotNull()
        & (col("montant_total") >= 0)
    )

    total_source = df_clean.count()
    total_valid = df_valid.count()
    total_rejected = total_source - total_valid

    print("Lignes source :", total_source)
    print("Lignes valides :", total_valid)
    print("Lignes rejetées :", total_rejected)

    # Ajout de la date de préparation Curated
    df_curated = df_valid.withColumn(
        "curated_at",
        current_timestamp()
    )

    print("=" * 60)
    print("ETAPE 3 - Aperçu des données Curated")

    df_curated.select(
        "_company_id",
        "id",
        "numero",
        "statut",
        "montant_total",
        "curated_at"
    ).show(truncate=False)

    print("=" * 60)
    print("ETAPE 4 - Ecriture dans MinIO")

    (
        df_curated.write
        .mode("overwrite")
        .partitionBy("_company_id")
        .parquet(TARGET_PATH)
    )

    print("Curated terminé :", TARGET_PATH)
    print("Nombre de lignes écrites :", total_valid)
    print("Partitionnement par entreprise : _company_id")
    print("=" * 60)

finally:
    spark.stop()
