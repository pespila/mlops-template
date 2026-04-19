"""Training-container entrypoint.

Reads configuration from env vars set by the platform worker:

    RUN_ID             — platform Run id
    DATASET_URI        — s3://... signed URL pointing at the dataset
    TRANSFORM_CONFIG   — JSON string describing feature transforms + target + split
    MODEL_CATALOG      — JSON string describing which adapter + hyperparams
    MLFLOW_TRACKING_URI, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY — MLflow/S3 access

Real implementation lands in the next commit. This file exists so the base
image builds and the import graph is valid.
"""

from __future__ import annotations

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    run_id = os.environ.get("RUN_ID", "unknown")
    logger.info("trainer.start run_id=%s", run_id)
    config = {
        "dataset_uri": os.environ.get("DATASET_URI"),
        "transform_config": os.environ.get("TRANSFORM_CONFIG"),
        "model_catalog": os.environ.get("MODEL_CATALOG"),
    }
    logger.info("trainer.config %s", json.dumps(config, default=str))
    logger.warning("trainer.not_implemented — real training logic arrives in the next commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
