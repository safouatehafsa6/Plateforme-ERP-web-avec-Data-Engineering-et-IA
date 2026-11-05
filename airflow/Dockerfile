FROM apache/spark:3.5.3 AS spark

FROM apache/airflow:2.9.3

USER root

COPY --from=spark /opt/java/openjdk /opt/java/openjdk

COPY --from=spark /opt/spark /opt/spark

RUN curl -fSL -o /opt/spark/jars/hadoop-aws-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
 && curl -fSL -o /opt/spark/jars/aws-java-sdk-s3-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-s3/1.12.262/aws-java-sdk-s3-1.12.262.jar \
 && curl -fSL -o /opt/spark/jars/aws-java-sdk-core-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-core/1.12.262/aws-java-sdk-core-1.12.262.jar \
 && curl -fSL -o /opt/spark/jars/aws-java-sdk-dynamodb-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-dynamodb/1.12.262/aws-java-sdk-dynamodb-1.12.262.jar \
 && curl -fSL -o /opt/spark/jars/postgresql-42.7.4.jar https://jdbc.postgresql.org/download/postgresql-42.7.4.jar \
 && chown -R airflow:root /opt/spark

ENV JAVA_HOME=/opt/java/openjdk
ENV SPARK_HOME=/opt/spark
ENV PATH=/home/airflow/.local/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin

USER airflow

RUN pip install --no-cache-dir minio==7.2.9