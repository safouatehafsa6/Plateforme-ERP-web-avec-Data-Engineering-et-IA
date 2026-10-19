"""Etape 3 - STAGING -> CURATED (commandes), pour le run courant.

Le resultat est ecrit dans un dossier propre au run :
    curated/commandes/run_id=<run_id>/_company_id=<n>/...
Le dossier n'est expose au Dashboard qu'apres succes du controle qualite
(quality_checks_curated.py), qui publie le pointeur curated/_meta/latest_success.json.
"""
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType

from pipeline_common import build_spark, get_run_id, lake_uri

REQUIRED = ["_company_id", "id", "client_id", "date_commande", "statut", "montant_total"]
OPTIONAL = ["numero", "date_modification"]  # colonnes metier utiles si presentes
# Volontairement exclus : notes (texte libre), devis_id, colonnes techniques.


def main():
    run_id = get_run_id()
    source_path = f"{lake_uri('staging')}/company_*/public/commande/commande_{run_id}"
    target_path = f"{lake_uri('curated')}/commandes/run_id={run_id}"
    rejected_path = f"{lake_uri('staging')}/rejected/commandes/run_id={run_id}"

    spark = build_spark("ERP-Commandes-Curated")
    try:
        df = spark.read.parquet(source_path)  # echoue si aucun fichier pour ce run

        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            raise RuntimeError(f"Colonnes obligatoires absentes du staging : {missing}")

        selected = REQUIRED + [c for c in OPTIONAL if c in df.columns]
        df = df.select(*selected)

        for field in ("numero", "statut"):
            if field in df.columns:
                df = df.withColumn(field, F.trim(F.col(field)))

        df = (
            df.withColumn(
                "montant_total",
                F.regexp_replace(F.trim(F.col("montant_total").cast("string")), ",", ".")
                .cast(DecimalType(18, 2)),
            )
            .withColumn("date_commande", F.to_timestamp(F.col("date_commande")))
        )

        is_valid = (
            F.col("id").isNotNull()
            & F.col("_company_id").isNotNull()
            & (F.col("_company_id") > 0)
            & F.col("montant_total").isNotNull()
            & (F.col("montant_total") >= 0)
        )

        valid = df.filter(is_valid)
        rejected = df.filter(~is_valid)

        total, kept = df.count(), valid.count()
        n_rejected = total - kept
        print(f"Run {run_id} | source={total} | valides={kept} | rejetees={n_rejected}")

        if n_rejected:
            # Trace d'audit : cles seulement, pas de donnees metier.
            rejected.select("_company_id", "id").write.mode("overwrite").parquet(rejected_path)

        curated = (
            valid.withColumn("_run_id", F.lit(run_id))
            .withColumn("curated_at", F.current_timestamp())
        )
        curated.write.mode("overwrite").partitionBy("_company_id").parquet(target_path)
        print(f"Curated ecrit : {target_path}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
