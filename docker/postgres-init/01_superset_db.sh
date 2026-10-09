#!/bin/bash
# срабатывает только на пустом томе; базу Airflow создаёт сам образ, тут база Superset
set -e

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v su_user="$SUPERSET_DB_USER" \
    -v su_password="$SUPERSET_DB_PASSWORD" \
    -v su_db="$SUPERSET_DB" <<'EOSQL'
    CREATE USER :"su_user" WITH PASSWORD :'su_password';
    CREATE DATABASE :"su_db" OWNER :"su_user";
EOSQL
