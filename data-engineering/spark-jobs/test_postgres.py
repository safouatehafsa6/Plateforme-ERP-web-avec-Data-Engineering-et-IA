from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("TestPostgreSQLERP") \
    .getOrCreate()

jdbc_url = "jdbc:postgresql://postgres-erp:5432/compte_societe_test_09855a07"

properties = {
    "user": "erp_user",
    "password": "erp_password",
    "driver": "org.postgresql.Driver"
}

df = spark.read.jdbc(
    url=jdbc_url,
    table="client",
    properties=properties
)

print("===== CLIENTS ERP =====")
print("Nombre de clients :", df.count())
df.show()

spark.stop()
