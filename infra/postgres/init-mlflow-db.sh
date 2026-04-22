#!/bin/bash
# Postgres init-script — runs once on fresh pgdata volume creation.
# Creates a second database `mlflow` owned by the same POSTGRES_USER as
# the main platform DB so MLflow can persist its metadata alongside our
# own without needing a second Postgres service.
#
# Runs during postgres:16-alpine's docker-entrypoint.sh bootstrap. If
# pgdata already exists (existing install), this script is NOT re-run —
# apply it by hand with:
#   docker compose exec postgres psql -U $POSTGRES_USER -c "CREATE DATABASE mlflow OWNER $POSTGRES_USER;"

set -eu

psql --username "${POSTGRES_USER}" --dbname postgres <<-SQL
  SELECT 'CREATE DATABASE mlflow OWNER ${POSTGRES_USER}'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow')\\gexec
SQL
