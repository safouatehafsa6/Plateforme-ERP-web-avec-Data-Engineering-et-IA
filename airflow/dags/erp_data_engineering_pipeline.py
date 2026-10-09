from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


with DAG(
    dag_id="erp_data_engineering_pipeline",
    start_date=datetime(2026, 10, 1),
    schedule=None,
    catchup=False,
    tags=["ERP", "Data Engineering", "Spark", "MinIO"],
) as dag:

    etl_erp = BashOperator(
        task_id="etl_erp_spark",
        bash_command="""
        /opt/spark/bin/spark-submit \
          --master spark://spark-master:7077 \
          --deploy-mode client \
          --jars /opt/spark/jars/postgresql-42.7.4.jar,/opt/spark/jars/hadoop-aws-3.3.4.jar,/opt/spark/jars/aws-java-sdk-s3-1.12.262.jar,/opt/spark/jars/aws-java-sdk-core-1.12.262.jar,/opt/spark/jars/aws-java-sdk-dynamodb-1.12.262.jar \
          /opt/spark/jobs/etl_erp.py
        """,
    )
