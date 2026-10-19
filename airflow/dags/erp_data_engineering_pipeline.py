"""Pipeline Data Engineering de l'ERP.

extract_raw -> transform_staging -> build_curated -> quality_gate

- Chaque execution a un PIPELINE_RUN_ID unique : un run ne lit jamais les
  donnees d'un run precedent.
- Le Dashboard n'affiche que le jeu de donnees publie par `quality_gate`
  (curated/_meta/latest_success.json). Si un controle echoue, rien n'est
  publie et le dernier jeu valide reste affiche.
- Declenchement : manuel, ou via l'API FastAPI (POST /api/pipeline/run) qui
  peut fournir son propre identifiant : conf={"pipeline_run_id": "..."}.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

JOBS = "/opt/spark/jobs"

SPARK_JARS = ",".join(
    f"/opt/spark/jars/{jar}"
    for jar in (
        "postgresql-42.7.4.jar",
        "hadoop-aws-3.3.4.jar",
        "aws-java-sdk-s3-1.12.262.jar",
        "aws-java-sdk-core-1.12.262.jar",
        "aws-java-sdk-dynamodb-1.12.262.jar",
    )
)

# Valide par les jobs (^[A-Za-z0-9_-]{8,64}$) : jamais interpole dans la commande shell.
RUN_ID = "{{ dag_run.conf.get('pipeline_run_id') or ts_nodash }}"


def spark_submit(script: str) -> str:
    return (
        "/opt/spark/bin/spark-submit "
        "--master spark://spark-master:7077 --deploy-mode client "
        f"--jars {SPARK_JARS} "
        f"--py-files {JOBS}/pipeline_common.py "
        f"{JOBS}/{script}"
    )


def job(task_id: str, command: str, timeout_minutes: int) -> BashOperator:
    return BashOperator(
        task_id=task_id,
        bash_command=command,
        env={"PIPELINE_RUN_ID": RUN_ID},
        append_env=True,  # garde ERP_DB_*, MINIO_* definis sur le conteneur
        execution_timeout=timedelta(minutes=timeout_minutes),
    )


with DAG(
    dag_id="erp_data_engineering_pipeline",
    start_date=datetime(2026, 10, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,  # jamais deux pipelines en parallele
    dagrun_timeout=timedelta(hours=1),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
    tags=["ERP", "Data Engineering", "Spark", "MinIO"],
    doc_md=__doc__,
) as dag:

    extract_raw = job(
        "extract_raw",
        f"python {JOBS}/extract_commandes_to_minio.py",
        timeout_minutes=15,
    )

    transform_staging = job(
        "transform_staging", spark_submit("transform_commandes.py"), timeout_minutes=20
    )

    build_curated = job(
        "build_curated", spark_submit("build_curated_commandes.py"), timeout_minutes=20
    )

    # Aucune retentative : un controle qualite refuse ne doit pas etre rejoue.
    quality_gate = BashOperator(
        task_id="quality_gate",
        bash_command=spark_submit("quality_checks_curated.py"),
        env={"PIPELINE_RUN_ID": RUN_ID},
        append_env=True,
        execution_timeout=timedelta(minutes=15),
        retries=0,
    )

    extract_raw >> transform_staging >> build_curated >> quality_gate
