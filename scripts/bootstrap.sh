#!/usr/bin/env bash
# Bootstrap the local stack: create MinIO buckets, run Alembic migrations,
# seed the admin user. Intended to run once after `make up`.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[bootstrap] bootstrap.sh runs in the next commit"
