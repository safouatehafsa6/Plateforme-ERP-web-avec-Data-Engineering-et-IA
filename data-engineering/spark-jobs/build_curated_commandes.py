
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, trim, current_timestamp

SOURCE_PATH = "s3a://staging/commandes/run_20261010T175907Z"
TARGET_PATH = "s3a://curated/commandes"

spark = (
    SparkSession.builder
    .appName("ERP-Commandes-Curated")
    .getOrCreate()
)

try:
    # Lire les données transformées depuis staging
    df = spark.read.parquet(SOURCE_PATH)

    # Contrôler et nettoyer les données
    df = (
        df.withColumn("statut", trim(col("statut")))
        .withColumn("numero", trim(col("numero")))
    )

    # Ne conserver que les enregistrements valides
    df_valid = df.filter(
        col("id").isNotNull()
        & col("company_id").isNotNull()
        & (col("company_id") > 0)
        & col("montant_total").isNotNull()
        & (col("montant_total") >= 0)
    )

    # Ajouter la date de préparation analytique
    df_curated = df_valid.withColumn(
        "curated_at", current_timestamp()
    )

    print("=== Données prêtes pour l'analyse ===")
    df_curated.printSchema()
    df_curated.show(truncate=False)

    # Écrire dans la couche curated en Parquet
    (
        df_curated.write
        .mode("overwrite")
        .parquet(TARGET_PATH)
    )

    print(f"Curated terminé : {TARGET_PATH}")
    print(f"Lignes valides : {df_curated.count()}")

finally:
    spark.stop()
