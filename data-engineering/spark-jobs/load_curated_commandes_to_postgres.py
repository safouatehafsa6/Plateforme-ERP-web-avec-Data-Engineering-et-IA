
import os
from pyspark.sql import SparkSession

SOURCE_PATH = "s3a://curated/commandes"
JDBC_URL = "jdbc:postgresql://postgres-erp:5432/erp_analytics"
JDBC_USER = "erp_user"
TARGET_TABLE = "fact_commandes"

password = os.environ.get("ERP_DB_PASSWORD")
if not password:
    raise RuntimeError("ERP_DB_PASSWORD n'est pas défini.")

spark = (
    SparkSession.builder
    .appName("ERP-Load-Commandes-Analytics")
    .getOrCreate()
)

try:
    # Lire les données déjà préparées par Spark
    df = spark.read.parquet(SOURCE_PATH)

    print(f"Lignes à charger : {df.count()}")

    # Vérifier que la table cible est vide avant le premier chargement.
    # Cela évite les doublons si le script est relancé.
    existing = (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", "(SELECT COUNT(*) AS n FROM fact_commandes) AS check_table")
        .option("user", JDBC_USER)
        .option("password", password)
        .option("driver", "org.postgresql.Driver")
        .load()
        .first()["n"]
    )

    if existing > 0:
        raise RuntimeError(
            f"La table contient déjà {existing} lignes. "
            "Chargement annulé pour éviter les doublons."
        )

    (
        df.write.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", TARGET_TABLE)
        .option("user", JDBC_USER)
        .option("password", password)
        .option("driver", "org.postgresql.Driver")
        .option("batchsize", "500")
        .mode("append")
        .save()
    )

    print("Chargement terminé avec succès.")

finally:
    spark.stop()
