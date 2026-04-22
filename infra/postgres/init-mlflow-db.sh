#!/bin/bash
# Postgres init-script — runs once on fresh pgdata volume creation.
# Creates the MLflow backend-store database owned by the same
# POSTGRES_USER as the main platform DB so MLflow can persist its
# metadata alongside our own without needing a second Postgres service.
#
# Database name comes from POSTGRES_MLFLOW_DB (defaults to "mlflow").
#
# Runs during postgres:16-alpine's docker-entrypoint.sh bootstrap. If
# pgdata already exists (existing install), this script is NOT re-run —
# apply it by hand with:
#   docker compose exec postgres psql -U $POSTGRES_USER \
#     -c "CREATE DATABASE ${POSTGRES_MLFLOW_DB} OWNER ${POSTGRES_USER};"

set -eu

DB_NAME="${POSTGRES_MLFLOW_DB:-mlflow}"

psql --username "${POSTGRES_USER}" --dbname postgres <<-SQL
  SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${POSTGRES_USER}'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\\gexec
SQL
