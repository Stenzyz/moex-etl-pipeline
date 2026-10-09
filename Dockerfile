FROM apache/airflow:3.3.0-python3.12

# java нужна драйверу Spark: spark-submit запускается из задачи Airflow в client-режиме
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt apache-airflow-providers-apache-spark==6.3.2
