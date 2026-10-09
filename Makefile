ifeq (,$(wildcard .env))
$(error .env not found. Run: cp .env.example .env - then fill in the values)
endif

include .env
export

CH_DIR = ./clickhouse
JARS_DIR = ./jars
MAVEN = https://repo1.maven.org/maven2
# версии под Hadoop 3.4.2, который лежит внутри Spark/pyspark 4.1.3
HADOOP_AWS_JAR = hadoop-aws-3.4.2.jar
AWS_SDK_JAR = bundle-2.29.52.jar
AIRFLOW_EXEC = docker compose exec -T airflow-scheduler
CH_CLIENT = docker compose exec -T clickhouse clickhouse-client \
	--user $(CLICKHOUSE_USER) --password $(CLICKHOUSE_PASSWORD) --multiquery

# make backfill FROM=2025-09-01 TILL=2026-09-01
FROM ?=
TILL ?=

.PHONY: all init jars build up down clean wait gen-keys ch-migrate create-bucket \
	explore ingest backfill test lint ps

all: init

init: jars build up wait ch-migrate create-bucket
	@echo ""
	@echo "Setup complete."
	@echo "  Airflow:    http://localhost:$(AIRFLOW_PORT)"
	@echo "  Superset:   http://localhost:$(SUPERSET_PORT)"
	@echo "  ClickHouse: http://localhost:$(CLICKHOUSE_HTTP_PORT)/play"
	@echo "  MinIO:      http://localhost:$(MINIO_CONSOLE_PORT)"
	@echo "  Spark UI:   http://localhost:$(SPARK_UI_PORT)"

# s3a для Spark; bundle весит несколько сотен МБ, качается один раз.
# через .tmp, чтобы оборванная загрузка не выглядела как готовый файл
jars:
	@mkdir -p $(JARS_DIR)
	@[ -f $(JARS_DIR)/$(HADOOP_AWS_JAR) ] || \
		(curl -fL -o $(JARS_DIR)/$(HADOOP_AWS_JAR).tmp \
			$(MAVEN)/org/apache/hadoop/hadoop-aws/3.4.2/$(HADOOP_AWS_JAR) \
		&& mv $(JARS_DIR)/$(HADOOP_AWS_JAR).tmp $(JARS_DIR)/$(HADOOP_AWS_JAR))
	@[ -f $(JARS_DIR)/$(AWS_SDK_JAR) ] || \
		(curl -fL -o $(JARS_DIR)/$(AWS_SDK_JAR).tmp \
			$(MAVEN)/software/amazon/awssdk/bundle/2.29.52/$(AWS_SDK_JAR) \
		&& mv $(JARS_DIR)/$(AWS_SDK_JAR).tmp $(JARS_DIR)/$(AWS_SDK_JAR))

# COMPOSE_BAKE=false: параллельный сборщик bake роняет BuildKit на этих образах
build:
	COMPOSE_BAKE=false docker compose build

up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

wait:
	@echo "Waiting for clickhouse..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' $$(docker compose ps -q clickhouse))" = "healthy" ]; do \
		printf "."; sleep 2; \
	done
	@echo " ready"
	@echo "Waiting for airflow-scheduler..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' $$(docker compose ps -q airflow-scheduler))" = "healthy" ]; do \
		printf "."; sleep 3; \
	done
	@echo " ready"

clean:
	@echo "WARNING: this removes ALL volumes - raw data, ClickHouse, Airflow and Superset metadata."
	@printf "Type 'yes' to continue: " && read ans && [ "$$ans" = "yes" ]
	docker compose down -v

gen-keys:
	@echo "FERNET_KEY=$$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
	@echo "AIRFLOW_JWT_SECRET=$$(openssl rand -hex 32)"
	@echo "SUPERSET_SECRET_KEY=$$(openssl rand -base64 42)"
	@echo ""
	@echo "Copy these into your .env"

# гоняется при каждом init, поэтому все скрипты только с IF NOT EXISTS
ch-migrate:
	@for file in $$(ls $(CH_DIR)/*.sql | sort); do \
		echo "Running $$file..."; \
		$(CH_CLIENT) < "$$file" || exit 1; \
	done
	@echo "ClickHouse migrations OK"

create-bucket:
	$(AIRFLOW_EXEC) python /opt/airflow/scripts/create_bucket.py

# разведка ISS, результат идёт в docs/scope.md
explore:
	$(AIRFLOW_EXEC) python /opt/airflow/scripts/explore_iss.py

# прямой запуск загрузчика, без Airflow: make ingest FROM=2026-09-01 TILL=2026-09-30
ingest:
	@if [ -z "$(FROM)" ] || [ -z "$(TILL)" ]; then \
		echo "Usage: make ingest FROM=YYYY-MM-DD TILL=YYYY-MM-DD"; exit 1; \
	fi
	$(AIRFLOW_EXEC) python -m ingest.load_candles \
		--date-from $(FROM) --date-till $(TILL)

# DAG moex_backfill появится на этапе 6
backfill:
	@if [ -z "$(FROM)" ] || [ -z "$(TILL)" ]; then \
		echo "Usage: make backfill FROM=YYYY-MM-DD TILL=YYYY-MM-DD"; exit 1; \
	fi
	$(AIRFLOW_EXEC) airflow dags trigger moex_backfill \
		--conf '{"date_from": "$(FROM)", "date_till": "$(TILL)"}'

test:
	pytest

lint:
	ruff check .
	ruff format --check .
