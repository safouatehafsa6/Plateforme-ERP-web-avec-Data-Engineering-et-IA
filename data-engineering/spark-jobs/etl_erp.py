from pyspark.sql import SparkSession
from pyspark.sql.functions import col, coalesce, lit, round, sum as spark_sum
from pyspark.sql.types import DecimalType

spark = SparkSession.builder \
    .appName("ERP_Data_Engineering_ETL") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minio_admin") \
    .config("spark.hadoop.fs.s3a.secret.key", "minio_password") \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

jdbc_url = "jdbc:postgresql://postgres-erp:5432/compte_societe_test_09855a07"

properties = {
    "user": "erp_user",
    "password": "erp_password",
    "driver": "org.postgresql.Driver"
}

def read_table(table):
    return spark.read.jdbc(
        url=jdbc_url,
        table=table,
        properties=properties
    )

def write_parquet(df, path):
    df.write.mode("overwrite").parquet(path)

print("========================================")
print("     ERP DATA ENGINEERING ETL")
print("========================================")

print("\n[1] Extraction PostgreSQL")

commande = read_table("commande")
ligne_commande = read_table("ligne_commande")
produit = read_table("produit")
client = read_table("client")

facture = read_table("facture")
ligne_facture = read_table("ligne_facture")

achat = read_table("achat")
ligne_achat = read_table("ligne_achat")
fournisseur = read_table("fournisseur")

print("commande :", commande.count())
print("ligne_commande :", ligne_commande.count())
print("produit :", produit.count())
print("client :", client.count())
print("facture :", facture.count())
print("ligne_facture :", ligne_facture.count())
print("achat :", achat.count())
print("ligne_achat :", ligne_achat.count())
print("fournisseur :", fournisseur.count())

print("\n[2] RAW - stockage des données sources")

write_parquet(commande, "s3a://raw/commande")
write_parquet(ligne_commande, "s3a://raw/ligne_commande")
write_parquet(produit, "s3a://raw/produit")
write_parquet(client, "s3a://raw/client")
write_parquet(facture, "s3a://raw/facture")
write_parquet(ligne_facture, "s3a://raw/ligne_facture")
write_parquet(achat, "s3a://raw/achat")
write_parquet(ligne_achat, "s3a://raw/ligne_achat")
write_parquet(fournisseur, "s3a://raw/fournisseur")

print("RAW terminé")

print("\n[3] STAGING - préparation des ventes")

ventes_staging = ligne_commande.alias("lc") \
    .join(
        commande.alias("c"),
        col("lc.commande_id") == col("c.id"),
        "inner"
    ) \
    .join(
        client.alias("cl"),
        col("c.client_id") == col("cl.id"),
        "left"
    ) \
    .join(
        produit.alias("p"),
        col("lc.produit_id") == col("p.id"),
        "left"
    ) \
    .select(
        col("c.id").alias("commande_id"),
        col("c.numero").alias("numero_commande"),
        col("c.date_commande"),
        col("c.statut").alias("statut_commande"),
        col("c.client_id"),
        col("cl.nom").alias("client_nom"),
        col("lc.produit_id"),
        col("p.reference").alias("produit_reference"),
        col("p.nom").alias("produit_nom"),
        col("p.categorie").alias("categorie"),
        col("lc.quantite"),
        col("lc.prix_unitaire"),
        col("lc.remise_pct")
    )

ventes_staging = ventes_staging \
    .withColumn(
        "montant_brut",
        col("quantite") * col("prix_unitaire")
    ) \
    .withColumn(
        "montant_remise",
        col("montant_brut") * col("remise_pct") / lit(100)
    ) \
    .withColumn(
        "montant_net",
        round(col("montant_brut") - col("montant_remise"), 2)
    )

write_parquet(ventes_staging, "s3a://staging/ventes")

print("STAGING ventes terminé")
print("Nombre de lignes ventes :", ventes_staging.count())

print("\n[4] CURATED - dataset ventes")

ventes_curated = ventes_staging.select(
    "commande_id",
    "numero_commande",
    "date_commande",
    "statut_commande",
    "client_id",
    "client_nom",
    "produit_id",
    "produit_reference",
    "produit_nom",
    "categorie",
    "quantite",
    "prix_unitaire",
    "remise_pct",
    "montant_brut",
    "montant_remise",
    "montant_net"
)

write_parquet(ventes_curated, "s3a://curated/ventes")

print("CURATED ventes terminé")

print("\n[5] STAGING - facturation")

factures_staging = ligne_facture.alias("lf") \
    .join(
        facture.alias("f"),
        col("lf.facture_id") == col("f.id"),
        "inner"
    ) \
    .join(
        produit.alias("p"),
        col("lf.produit_id") == col("p.id"),
        "left"
    ) \
    .join(
        commande.alias("c"),
        col("f.commande_id") == col("c.id"),
        "left"
    ) \
    .join(
        client.alias("cl"),
        col("c.client_id") == col("cl.id"),
        "left"
    ) \
    .select(
        col("f.id").alias("facture_id"),
        col("f.numero").alias("numero_facture"),
        col("f.date_facture"),
        col("f.statut").alias("statut_facture"),
        col("f.commande_id"),
        col("c.client_id"),
        col("cl.nom").alias("client_nom"),
        col("lf.produit_id"),
        col("p.reference").alias("produit_reference"),
        col("lf.designation").alias("designation"),
        col("lf.quantite"),
        col("lf.prix_unitaire"),
        col("lf.remise_pct")
    )

factures_staging = factures_staging \
    .withColumn(
        "montant_brut",
        col("quantite") * col("prix_unitaire")
    ) \
    .withColumn(
        "montant_remise",
        col("montant_brut") * col("remise_pct") / lit(100)
    ) \
    .withColumn(
        "montant_net",
        round(col("montant_brut") - col("montant_remise"), 2)
    )

write_parquet(factures_staging, "s3a://staging/factures")

print("STAGING factures terminé")

print("\n[6] CURATED - dataset factures")

write_parquet(
    factures_staging,
    "s3a://curated/factures"
)

print("CURATED factures terminé")

print("\n[7] STAGING - achats")

achats_staging = ligne_achat.alias("la") \
    .join(
        achat.alias("a"),
        col("la.achat_id") == col("a.id"),
        "inner"
    ) \
    .join(
        fournisseur.alias("fr"),
        col("a.fournisseur_id") == col("fr.id"),
        "left"
    ) \
    .join(
        produit.alias("p"),
        col("la.produit_id") == col("p.id"),
        "left"
    ) \
    .select(
        col("a.id").alias("achat_id"),
        col("a.numero").alias("numero_achat"),
        col("a.date_achat"),
        col("a.statut").alias("statut_achat"),
        col("a.fournisseur_id"),
        col("fr.nom").alias("fournisseur_nom"),
        col("la.produit_id"),
        col("p.reference").alias("produit_reference"),
        col("p.nom").alias("produit_nom"),
        col("p.categorie").alias("categorie"),
        col("la.quantite"),
        col("la.prix_unitaire")
    )

achats_staging = achats_staging.withColumn(
    "montant_achat",
    round(col("quantite") * col("prix_unitaire"), 2)
)

write_parquet(achats_staging, "s3a://staging/achats")

print("STAGING achats terminé")

print("\n[8] CURATED - dataset achats")

write_parquet(
    achats_staging,
    "s3a://curated/achats"
)

print("CURATED achats terminé")

print("\n[9] VERIFICATION")

print("\n===== CURATED VENTES =====")
ventes_curated.show(20, truncate=False)

print("\n===== CURATED FACTURES =====")
factures_staging.show(20, truncate=False)

print("\n===== CURATED ACHATS =====")
achats_staging.show(20, truncate=False)

print("\n========================================")
print("       ETL ERP TERMINE AVEC SUCCES")
print("========================================")
print("Datasets disponibles :")
print("s3a://curated/ventes")
print("s3a://curated/factures")
print("s3a://curated/achats")

spark.stop()
