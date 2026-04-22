#!/usr/bin/env bash
# AIpacken local backup — no cloud, no external services.
#
# What it backs up:
#   * Postgres: pg_dump (custom format) of the platform database from
#     the running compose-postgres-1 container.
#   * platform-data volume: tar.gz of /var/platform-data from inside
#     the running api container (which has it bind-mounted). Covers
#     datasets, run artifacts, models, packages, Traefik dynamic
#     routes, MLflow artifact root once it lands.
#
# Where it writes:
#   ./backups/<timestamp>/
#       platform.sql.gz      (compressed pg_dump -Fc output)
#       platform-data.tar.gz (tar of /var/platform-data)
#       MANIFEST.json        (what was captured, when, compose status)
#
# Retention: last 14 days are kept. Override with BACKUP_RETENTION_DAYS.
#
# Usage:
#   ./scripts/backup.sh                 # ad-hoc, writes to ./backups/
#   BACKUP_DIR=/mnt/nas ./scripts/backup.sh
#   BACKUP_RETENTION_DAYS=30 ./scripts/backup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

COMPOSE_FILE="${REPO_ROOT}/infra/compose/docker-compose.yml"
ENV_FILE="${REPO_ROOT}/.env"
DOCKER="${DOCKER:-docker}"

# Resolve Docker Desktop's binary if it wasn't symlinked onto $PATH.
if ! command -v "${DOCKER}" >/dev/null 2>&1; then
  if [[ -x /Applications/Docker.app/Contents/Resources/bin/docker ]]; then
    DOCKER=/Applications/Docker.app/Contents/Resources/bin/docker
  else
    echo "[backup] docker binary not found on PATH" >&2
    exit 1
  fi
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[backup] ${ENV_FILE} missing. Run 'make .env' first." >&2
  exit 1
fi

# Read POSTGRES_USER / POSTGRES_DB from .env without sourcing the whole file.
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "${ENV_FILE}" | cut -d= -f2-)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' "${ENV_FILE}" | cut -d= -f2-)

TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_DIR}/${TS}"
mkdir -p "${DEST}"

echo "[backup] writing to ${DEST}"

# 1) Postgres dump (custom format so restore can be parallel/selective).
echo "[backup] pg_dump ${POSTGRES_DB} -> platform.sql.gz"
"${DOCKER}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T postgres \
  pg_dump --format=custom --compress=9 --no-owner --no-acl \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
  > "${DEST}/platform.sql.gz"

# 2) platform-data tar — run it from inside the api container which has
#    the volume bind-mounted read-write. Stream straight to the host via
#    `docker exec`'s stdout so we don't need a temp file in the container.
echo "[backup] tar /var/platform-data -> platform-data.tar.gz"
"${DOCKER}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T api \
  tar --numeric-owner -cz -C /var platform-data \
  > "${DEST}/platform-data.tar.gz"

# 3) Manifest with enough context that a future human can answer 'what
#    was running when this was taken?'
"${DOCKER}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps --format json \
  > "${DEST}/compose-ps.json" 2>/dev/null || true

cat > "${DEST}/MANIFEST.json" <<EOF
{
  "timestamp": "${TS}",
  "hostname": "$(hostname)",
  "postgres_user": "${POSTGRES_USER}",
  "postgres_db": "${POSTGRES_DB}",
  "platform_data_bytes": $(stat -f%z "${DEST}/platform-data.tar.gz" 2>/dev/null || stat -c%s "${DEST}/platform-data.tar.gz"),
  "platform_sql_bytes":  $(stat -f%z "${DEST}/platform.sql.gz"      2>/dev/null || stat -c%s "${DEST}/platform.sql.gz"),
  "retention_days": ${RETENTION_DAYS}
}
EOF

# 4) Prune anything older than retention window.
if [[ -d "${BACKUP_DIR}" ]]; then
  echo "[backup] pruning backups older than ${RETENTION_DAYS} days"
  find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d \
    -mtime +"${RETENTION_DAYS}" -print -exec rm -rf {} +
fi

echo "[backup] done -> ${DEST}"
