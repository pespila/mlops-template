#!/usr/bin/env bash
# AIpacken local restore — pairs with scripts/backup.sh.
#
# Destructive: drops and re-creates the platform database, wipes the
# platform-data volume, then reinstates both from the snapshot.
#
# Usage:
#   ./scripts/restore.sh ./backups/20260422T142400Z
#   ./scripts/restore.sh /mnt/nas/20260422T142400Z

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

COMPOSE_FILE="${REPO_ROOT}/infra/compose/docker-compose.yml"
ENV_FILE="${REPO_ROOT}/.env"
DOCKER="${DOCKER:-docker}"

if ! command -v "${DOCKER}" >/dev/null 2>&1; then
  if [[ -x /Applications/Docker.app/Contents/Resources/bin/docker ]]; then
    DOCKER=/Applications/Docker.app/Contents/Resources/bin/docker
  else
    echo "[restore] docker binary not found on PATH" >&2
    exit 1
  fi
fi

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <backup-dir>" >&2
  echo "  example: $0 ./backups/20260422T142400Z" >&2
  exit 2
fi

SRC="$1"
if [[ ! -d "${SRC}" ]]; then
  echo "[restore] ${SRC} is not a directory" >&2
  exit 1
fi
for required in platform.sql.gz platform-data.tar.gz MANIFEST.json; do
  if [[ ! -f "${SRC}/${required}" ]]; then
    echo "[restore] ${SRC}/${required} missing" >&2
    exit 1
  fi
done

POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "${ENV_FILE}" | cut -d= -f2-)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' "${ENV_FILE}" | cut -d= -f2-)

echo "[restore] source:        ${SRC}"
echo "[restore] target db:     ${POSTGRES_DB} as ${POSTGRES_USER}"
echo "[restore] target volume: platform-data"
echo "[restore] THIS WILL DROP BOTH. Type 'yes' to continue:"
read -r confirm
if [[ "${confirm}" != "yes" ]]; then
  echo "[restore] aborted"
  exit 1
fi

echo "[restore] stopping api + worker-fast + worker-slow + builder so nothing writes during restore"
"${DOCKER}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" stop api worker-fast worker-slow builder || true

# ---- Postgres ---------------------------------------------------------
echo "[restore] re-creating database ${POSTGRES_DB}"
"${DOCKER}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T postgres \
  psql --username="${POSTGRES_USER}" --dbname=postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB} WITH (FORCE);" \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

echo "[restore] pg_restore platform.sql.gz"
"${DOCKER}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T postgres \
  pg_restore --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --no-owner --no-acl --exit-on-error \
  < "${SRC}/platform.sql.gz"

# ---- platform-data ----------------------------------------------------
# Postgres is the only service still up. Mount the volume in a throwaway
# alpine container and untar into /var.
echo "[restore] wiping + restoring platform-data volume"
"${DOCKER}" run --rm -v platform-data:/var/platform-data alpine:3.20 \
  sh -c 'rm -rf /var/platform-data/* /var/platform-data/..?* /var/platform-data/.[!.]* 2>/dev/null || true'

"${DOCKER}" run --rm -i -v platform-data:/var/platform-data alpine:3.20 \
  tar -xz -C /var < "${SRC}/platform-data.tar.gz"

echo "[restore] starting services again"
"${DOCKER}" compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d

echo "[restore] done"
