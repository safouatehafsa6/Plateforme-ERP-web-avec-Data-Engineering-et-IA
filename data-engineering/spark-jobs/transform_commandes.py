
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, trim, when
from pyspark.sql.types import (
    StructType,
    StructField,
    IntegerType,
    StringType,
    DecimalType,
    TimestampType,
)

# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

SOURCE_PATH = (
    "s3a://raw/commandes/"
    "commandes_20261010T154403Z.jsonl"
)

OUTPUT_PATH = (
    "s3a://staging/commandes/"
    f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
)

# --------------------------------------------------
# 2. Schema des données
# --------------------------------------------------

schema = StructType([
    StructField("id", IntegerType(), True),
    StructField("client_id", IntegerType(), True),
    StructField("date_commande", StringType(), True),
    StructField("statut", StringType(), True),
    StructField("montant_total", DecimalType(18, 2), True),
    StructField("numero", StringType(), True),
    StructField("devis_id", IntegerType(), True),
    StructField("notes", StringType(), True),
    StructField("date_modification", StringType(), True),
    StructField("company_id", IntegerType(), False),
])

# --------------------------------------------------
# 3. Initialisation de Spark
# --------------------------------------------------

spark = (
    SparkSession.builder
    .appName("ERP-Commandes-Transformation")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

try:
    # --------------------------------------------------
    # 4. Lecture des données depuis MinIO / raw
    # --------------------------------------------------

    df = (
        spark.read
        .schema(schema)
        .option("mode", "FAILFAST")
        .json(SOURCE_PATH)
    )

    print("=== Données brutes ===")
    df.printSchema()

    total_initial = df.count()
    print(f"Nombre de lignes lues : {total_initial}")

    # --------------------------------------------------
    # 5. Nettoyage prudent
    # --------------------------------------------------

    df_clean = (
        df
        .withColumn("statut", trim(col("statut")))
        .withColumn(
            "statut",
            when(col("statut") == "", None)
            .otherwise(col("statut"))
        )
        .withColumn(
            "numero",
            when(trim(col("numero")) == "", None)
            .otherwise(trim(col("numero")))
        )
        .withColumn(
            "date_commande",
            col("date_commande").cast(TimestampType())
        )
        .withColumn(
            "date_modification",
            col("date_modification").cast(TimestampType())
        )
    )

    # On conserve les lignes : aucune suppression automatique.
    # On signale les lignes qui nécessitent une vérification.
    df_checked = df_clean.withColumn(
        "data_quality_status",
        when(col("id").isNull(), "INVALID_ID")
        .when(col("company_id").isNull(), "INVALID_COMPANY_ID")
        .when(col("montant_total") < 0, "NEGATIVE_AMOUNT")
        .otherwise("OK")
    )

    print("=== Résultat de la transformation ===")
    df_checked.printSchema()
    df_checked.show(truncate=False)

    print(f"Nombre de lignes après transformation : {df_checked.count()}")

    # --------------------------------------------------
    # 6. Écriture en Parquet dans MinIO / staging
    # --------------------------------------------------

    (
        df_checked.write
        .mode("errorifexists")
        .parquet(OUTPUT_PATH)
    )

    print(f"Transformation terminée : {OUTPUT_PATH}")

finally:
    spark.stop()
