from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("Inspect-Curated-Commandes").getOrCreate()
try:
    df = spark.read.parquet("s3a://curated/commandes")
    print("===== SCHEMA CURATED =====")
    df.printSchema()
    print("===== NOMBRE DE LIGNES =====")
    print(df.count())
    print("===== EXEMPLE =====")
    df.show(5, truncate=False)
finally:
    spark.stop()
