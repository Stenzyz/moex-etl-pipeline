FROM apache/superset:6.1.0

# clickhouse-connect заодно ставит SQLAlchemy-диалект clickhousedb://
USER root
RUN uv pip install --python /app/.venv/bin/python psycopg2-binary clickhouse-connect==1.9.0
USER superset
