# MLflow Tracking Server image with boto3 + psycopg2-binary pre-installed.
#
# Previously the compose file did `pip install …` at container start via
# the entrypoint. That worked but meant:
#   * 30-60 s cold-start while pip resolved + downloaded wheels,
#   * the /health probe failed for that entire window,
#   * a flaky network on container start meant MLflow might never come up,
#   * operators couldn't pre-warm or pre-cache the image.
#
# Baking the deps in keeps MLflow boot under 5 s and decouples the image
# from PyPI availability at runtime.

FROM ghcr.io/mlflow/mlflow:v2.17.2

# psycopg2-binary   -> Postgres backend store
# boto3             -> S3-compatible artifact store (our MinIO)
# pinned to the same versions the Batch 32 runtime install used.
RUN pip install --no-cache-dir \
      boto3==1.35.79 \
      psycopg2-binary==2.9.10

# The base image defaults to CMD ["mlflow"]. Our compose passes the real
# `server …` subcommand + all flags via command:, so no entrypoint change.
