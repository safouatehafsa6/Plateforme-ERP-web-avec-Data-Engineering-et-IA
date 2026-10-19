FROM apache/spark:3.5.3 AS spark

FROM apache/airflow:2.9.3

USER root

RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless procps curl && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=spark /opt/spark /opt/spark

RUN curl -fSL -o /opt/spark/jars/hadoop-aws-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
 && curl -fSL -o /opt/spark/jars/aws-java-sdk-s3-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-s3/1.12.262/aws-java-sdk-s3-1.12.262.jar \
 && curl -fSL -o /opt/spark/jars/aws-java-sdk-core-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-core/1.12.262/aws-java-sdk-core-1.12.262.jar \
 && curl -fSL -o /opt/spark/jars/aws-java-sdk-dynamodb-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-dynamodb/1.12.262/aws-java-sdk-dynamodb-1.12.262.jar \
 && curl -fSL -o /opt/spark/jars/postgresql-42.7.4.jar https://jdbc.postgresql.org/download/postgresql-42.7.4.jar \
 && chown -R airflow:root /opt/spark

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV SPARK_HOME=/opt/spark
ENV PATH=/home/airflow/.local/bin:/usr/lib/jvm/java-17-openjdk-amd64/bin:/usr/local/bin:/usr/bin:/bin

USER airflow

RUN pip install --no-cache-dir minio==7.2.9