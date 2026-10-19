"""Etape 4 - Controle qualite du curated + publication.

Si TOUS les controles passent :
  - rapport ecrit dans curated/_meta/quality/<run_id>.json
  - pointeur curated/_meta/latest_success.json mis a jour (c'est le SEUL
    fichier que FastAPI/Streamlit utilisent pour savoir quoi afficher)
Sinon : rapport ecrit, pointeur inchange (le Dashboard garde le dernier
jeu de donnees valide), et le job echoue (code retour 1) -> le DAG s'arrete.
"""
import json
import os
import sys
from datetime import datetime, timezone

from pyspark.sql import functions as F

from pipeline_common import build_spark, get_run_id, lake_uri, write_text


def main():
    run_id = get_run_id()
    max_reject_pct = float(os.environ.get("QUALITY_MAX_REJECT_PCT", "5"))
    max_montant = float(os.environ.get("QUALITY_MAX_MONTANT", "1000000000"))

    staging_path = f"{lake_uri('staging')}/company_*/public/commande/commande_{run_id}"
    dataset = f"commandes/run_id={run_id}"
    curated_path = f"{lake_uri('curated')}/{dataset}"
    meta_root = f"{lake_uri('curated')}/_meta"

    spark = build_spark("ERP-Quality-Gate")
    checks = []
    report = {"run_id": run_id, "checked_at": datetime.now(timezone.utc).isoformat()}

    def check(name, ok, detail):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        print(f"[{'OK ' if ok else 'KO '}] {name} : {detail}")

    try:
        staging = spark.read.parquet(staging_path)
        curated = spark.read.parquet(curated_path)
        n_staging, n_curated = staging.count(), curated.count()
        report["rows"] = n_curated

        check("donnees_presentes", n_curated > 0, f"{n_curated} ligne(s) curated")

        required = ["id", "_company_id", "date_commande", "statut", "montant_total"]
        nulls = curated.select(
            *[F.sum(F.col(c).isNull().cast("int")).alias(c) for c in required]
        ).first().asDict()
        nulls = {k: int(v or 0) for k, v in nulls.items()}
        check("colonnes_obligatoires_non_nulles", sum(nulls.values()) == 0, nulls)

        dupes = curated.groupBy("_company_id", "id").count().filter("count > 1").count()
        check("pas_de_doublons", dupes == 0, f"{dupes} cle(s) (entreprise, id) dupliquee(s)")

        bad_amount = curated.filter(
            (F.col("montant_total") < 0) | (F.col("montant_total") > max_montant)
        ).count()
        check("montants_coherents", bad_amount == 0,
              f"{bad_amount} montant(s) hors [0 ; {max_montant:g}]")

        bad_date = curated.filter(
            (F.col("date_commande") < F.lit("2000-01-01").cast("timestamp"))
            | (F.col("date_commande") > F.expr("current_timestamp() + INTERVAL 1 DAY"))
        ).count()
        check("dates_coherentes", bad_date == 0, f"{bad_date} date(s) hors plage")

        reject_pct = 0.0 if n_staging == 0 else (n_staging - n_curated) * 100.0 / n_staging
        check("taux_de_rejet", reject_pct <= max_reject_pct,
              f"{reject_pct:.2f}% rejete (seuil {max_reject_pct:g}%)")

        staging_companies = {r[0] for r in staging.select("_company_id").distinct().collect()}
        curated_by_company = {
            int(r[0]): int(r[1])
            for r in curated.groupBy("_company_id").count().collect()
        }
        lost = sorted(staging_companies - set(curated_by_company))
        check("aucune_entreprise_perdue", not lost, f"entreprises perdues : {lost}")
        report["companies"] = curated_by_company

        passed = all(c["passed"] for c in checks)
        report["passed"] = passed
        report["checks"] = checks
        write_text(spark, f"{meta_root}/quality/{run_id}.json",
                   json.dumps(report, ensure_ascii=False, default=str))

        if passed:
            write_text(
                spark,
                f"{meta_root}/latest_success.json",
                json.dumps({
                    "run_id": run_id,
                    "dataset": dataset,
                    "rows": n_curated,
                    "companies": curated_by_company,
                    "published_at": datetime.now(timezone.utc).isoformat(),
                }),
            )
            print(f"\nQUALITE VALIDEE - jeu de donnees publie : {dataset}")
        else:
            print("\nQUALITE REFUSEE - le dernier jeu valide reste affiche.")
        return 0 if passed else 1
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
