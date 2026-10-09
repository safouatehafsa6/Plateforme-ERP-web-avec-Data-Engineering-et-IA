from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("TestSparkMinIO") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minio_admin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minio_password") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
    .getOrCreate()

data = [
    ("test-1", "Spark", 100),
    ("test-2", "MinIO", 200),
    ("test-3", "ERP", 300)
]

df = spark.createDataFrame(data, ["id", "source", "valeur"])

output_path = "s3a://raw/test_spark_minio"

df.write.mode("overwrite").parquet(output_path)

print("===== TEST SPARK -> MINIO =====")
print("Écriture réussie :", output_path)

spark.stop()
