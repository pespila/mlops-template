#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker build -t platform/trainer-base:latest trainer_base/
docker build -t platform/serving-base:latest serving_base/
