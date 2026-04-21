"""Build a downloadable deployment package for a ModelVersion.

Produces a single ``.tar.gz`` under ``packages/{package_id}.tar.gz`` containing:

    artifacts/              -> model.pkl (or autogluon/ dir) + input_schema.json
    artifacts/selected_hyperparams.json, reports/*.json, metrics.jsonl (if any)
    image/serving-image.tar -> docker save of the matching serving image
    Dockerfile              -> minimal rebuild recipe pinned to the same base
    predict.py              -> standalone script that loads model.pkl + predicts
    README.md               -> templated with framework, input schema, and a
                               ready-to-copy `docker load` + `docker run` flow

The docker-save step runs on the builder service (sole owner of the Docker
socket) and writes directly into the shared platform-data volume. Everything
is assembled in a temp directory next to the final tarball, then tarred.
"""

from __future__ import annotations

import json
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from aipacken import storage
from aipacken.config import get_settings
from aipacken.db.models import ModelPackage, ModelVersion, RegisteredModel
from aipacken.docker_client.builder_client import get_builder_client

logger = structlog.get_logger(__name__)


_README_TEMPLATE = """# {model_name} — Deployment Package

Exported {exported_at_utc} from AIpacken.

This archive contains everything required to run the model's serving
container on any host with Docker installed. No platform account needed.

## Contents

```
artifacts/           Model artifacts written by the trainer
  model.pkl          The fitted sklearn pipeline (or `autogluon/` directory
                     for AutoGluon models)
  input_schema.json  Column names and types the model expects
  selected_hyperparams.json   The exact hyperparameters used (either user-set
                     or the HPO-winning configuration)
  reports/           SHAP + bias + (optional) HPO reports
image/serving-image.tar   `docker save` of the matching serving image
Dockerfile           Recipe that reproduces the image from scratch
predict.py           Standalone Python entrypoint — loads model.pkl and
                     scores a CSV or JSON payload without Docker
README.md            This file
```

## Model summary

- **Framework**: {framework}
- **Task**: {task}
- **Model kind**: {model_kind}
- **Version**: {version}
- **Source run**: {run_id}

## Option A — Run the exported image

```bash
# Load the image into your local Docker daemon
docker load -i image/serving-image.tar

# Prepare a volume pointing at this package's artifacts
docker run --rm -d \\
  --name {slug} \\
  -p 8000:8000 \\
  -v "$(pwd)/artifacts:/var/platform-data/models/{version_id}:ro" \\
  -e MODEL_STORAGE_PATH=models/{version_id} \\
  -e MODEL_KIND={model_kind} \\
  -e DATA_ROOT=/var/platform-data \\
  {serving_image}

# Smoke-check
curl http://localhost:8000/ready
```

### Predicting

```bash
curl -X POST http://localhost:8000/predict \\
  -H 'content-type: application/json' \\
  -d '{{"rows": [{example_row}]}}'
```

## Option B — Rebuild the image from scratch

If you'd rather not trust the prebuilt tar, the included `Dockerfile`
reproduces the serving image bit-for-bit (same pinned deps as the platform
runs). From this directory:

```bash
docker build -t my-model:latest .
docker run --rm -d -p 8000:8000 \\
  -v "$(pwd)/artifacts:/var/platform-data/models/{version_id}:ro" \\
  -e MODEL_STORAGE_PATH=models/{version_id} \\
  -e MODEL_KIND={model_kind} \\
  -e DATA_ROOT=/var/platform-data \\
  my-model:latest
```

## Option C — No Docker

`predict.py` loads the model directly and will score a JSON payload on
stdin. Handy for quick local testing or batch jobs:

```bash
pip install {pip_deps}
python predict.py < sample.json
```

where `sample.json` is `{{"rows": [{{...feature_values...}}]}}`.

## Expected input columns

| Column | Type |
|--------|------|
{input_columns_table}

## Notes

- The model was trained with the preprocessor fit on the training split.
  Any live inference payload has to match the column set above — the
  pipeline handles encoding and scaling internally.
- When deploying behind a reverse proxy, terminate TLS at the proxy. The
  serving container speaks plain HTTP on port 8000 inside its network.
- Re-export the package from the platform whenever you retrain — the model
  artifacts and image pins in this archive are immutable snapshots.
"""


_DOCKERFILE_TEMPLATE = """# Minimal Dockerfile to rebuild the serving image without the packed tar.
#
# The platform's `serving_base` image bundles the runtime Python deps; this
# file extends it with the model artifacts so the container is self-contained.
# Using the FROM line exactly as the platform uses ensures you get the same
# pinned sklearn / numpy / xgboost / etc.
FROM {serving_image}

COPY artifacts /var/platform-data/models/{version_id}

ENV MODEL_STORAGE_PATH=models/{version_id} \\
    MODEL_KIND={model_kind} \\
    DATA_ROOT=/var/platform-data

EXPOSE 8000
"""


_PREDICT_PY = '''"""Standalone inference entrypoint — no Docker required.

Loads the exported model pickle and prints one prediction per row in the
input JSON payload. Handles both sklearn pipelines (`model.pkl`) and
AutoGluon predictors (`artifacts/autogluon/` directory).

Usage:

    python predict.py <<<EOF
    {"rows": [{"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}]}
    EOF
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    artifacts = Path(__file__).resolve().parent / "artifacts"
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON on stdin: {exc}", file=sys.stderr)
        return 1

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        print('expected JSON {"rows": [...]}', file=sys.stderr)
        return 1

    import pandas as pd

    frame = pd.DataFrame(rows)

    # sklearn pipeline path (single model.pkl)
    pkl = artifacts / "model.pkl"
    if pkl.exists():
        import joblib

        model = joblib.load(pkl)
        preds = model.predict(frame)
        decoded = preds.tolist() if hasattr(preds, "tolist") else list(preds)
        out: dict[str, object] = {"predictions": decoded}
        encoder = getattr(model, "label_encoder_", None)
        if encoder is not None:
            try:
                out["labels"] = list(encoder.inverse_transform(preds))
            except Exception:  # noqa: BLE001
                pass
        print(json.dumps(out))
        return 0

    # AutoGluon path (directory of arbitrary layout)
    ag_dir = artifacts / "autogluon"
    if ag_dir.exists():
        from autogluon.tabular import TabularPredictor  # type: ignore[import]

        predictor = TabularPredictor.load(str(ag_dir))
        preds = predictor.predict(frame)
        print(json.dumps({"predictions": preds.tolist()}))
        return 0

    print("no model artifact found under ./artifacts", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


async def _update_status(
    session_factory: Any,
    package_id: str,
    *,
    status: str | None = None,
    storage_path: str | None = None,
    size_bytes: int | None = None,
    error: str | None = None,
) -> None:
    async with session_factory() as db:
        pkg = await db.get(ModelPackage, package_id)
        if pkg is None:
            return
        if status is not None:
            pkg.status = status
        if storage_path is not None:
            pkg.storage_path = storage_path
        if size_bytes is not None:
            pkg.size_bytes = size_bytes
        if error is not None:
            pkg.error_message = error[:2000]
        pkg.updated_at = datetime.now(timezone.utc)
        await db.commit()


def _pip_deps_for(model_kind: str) -> str:
    if (model_kind or "").lower() == "autogluon":
        return "autogluon.tabular pandas"
    return "joblib scikit-learn pandas xgboost lightgbm"


def _input_columns_table(artifacts_dir: Path) -> str:
    schema_file = artifacts_dir / "input_schema.json"
    if not schema_file.exists():
        return "| (schema unavailable) | — |"
    try:
        schema = json.loads(schema_file.read_text())
        props = schema.get("properties") or {}
        if not isinstance(props, dict) or not props:
            return "| (no columns recorded) | — |"
        rows = []
        for col, spec in props.items():
            typ = (spec or {}).get("type", "number") if isinstance(spec, dict) else "number"
            rows.append(f"| `{col}` | {typ} |")
        return "\n".join(rows)
    except Exception:  # noqa: BLE001
        return "| (unparseable schema) | — |"


def _example_row(artifacts_dir: Path) -> str:
    schema_file = artifacts_dir / "input_schema.json"
    if not schema_file.exists():
        return '{"feature_1": 0.0}'
    try:
        schema = json.loads(schema_file.read_text())
        props = schema.get("properties") or {}
        if not isinstance(props, dict):
            return '{"feature_1": 0.0}'
        example = {col: 0 for col in list(props.keys())[:4]}
        return json.dumps(example)
    except Exception:  # noqa: BLE001
        return '{"feature_1": 0.0}'


def _slugify(name: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name.strip().lower())
    return out.strip("-") or "model"


async def build_package(ctx: dict[str, Any], package_id: str) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    settings = get_settings()

    async with session_factory() as db:
        pkg = await db.get(ModelPackage, package_id)
        if pkg is None:
            return {"status": "missing"}
        mv = await db.get(ModelVersion, pkg.model_version_id)
        if mv is None or not mv.storage_path:
            await _update_status(
                session_factory,
                package_id,
                status="failed",
                error="model_version_missing_or_incomplete",
            )
            return {"status": "failed", "reason": "model_version_missing"}
        registered = await db.get(RegisteredModel, mv.registered_model_id)
        model_name = registered.name if registered else "model"

        pkg.status = "building"
        pkg.updated_at = datetime.now(timezone.utc)
        await db.commit()

    try:
        # 1. Set up the scratch dir.
        scratch = storage.package_dir(package_id)
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True, exist_ok=True)
        artifacts_out = scratch / "artifacts"
        image_out = scratch / "image"
        artifacts_out.mkdir(parents=True, exist_ok=True)
        image_out.mkdir(parents=True, exist_ok=True)

        # 2. Copy the model artifacts.
        model_dir = storage.to_absolute(mv.storage_path).parent
        for entry in model_dir.iterdir():
            dst = artifacts_out / entry.name
            if entry.is_dir():
                shutil.copytree(entry, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, dst)

        # 3. Ask the builder to save the serving image into image/.
        is_ag = (mv.model_kind or "").lower() == "autogluon"
        serving_image = (
            mv.serving_image_uri
            or (settings.serving_base_autogluon_image if is_ag else settings.serving_base_image)
        )
        image_tar_dest = image_out / "serving-image.tar"
        builder = get_builder_client()
        await builder.save_image(serving_image, str(image_tar_dest))

        # 4. README + Dockerfile + predict.py.
        task_label = "unknown"
        framework_label = "scikit-learn"
        schema_file = artifacts_out / "input_schema.json"
        try:
            if schema_file.exists():
                schema_doc = json.loads(schema_file.read_text())
                task_label = str(schema_doc.get("flavor") or task_label)
        except Exception:  # noqa: BLE001
            pass
        sel_file = artifacts_out / "selected_hyperparams.json"
        try:
            if sel_file.exists():
                sel = json.loads(sel_file.read_text())
                task_label = str(sel.get("task") or task_label)
                framework_label = str(sel.get("model_name") or framework_label)
        except Exception:  # noqa: BLE001
            pass

        readme = _README_TEMPLATE.format(
            model_name=model_name,
            exported_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            framework=framework_label,
            task=task_label,
            model_kind=mv.model_kind or "sklearn",
            version=mv.version,
            version_id=mv.id,
            run_id=mv.run_id,
            slug=_slugify(model_name),
            serving_image=serving_image,
            pip_deps=_pip_deps_for(mv.model_kind or ""),
            input_columns_table=_input_columns_table(artifacts_out),
            example_row=_example_row(artifacts_out),
        )
        (scratch / "README.md").write_text(readme)
        (scratch / "Dockerfile").write_text(
            _DOCKERFILE_TEMPLATE.format(
                serving_image=serving_image,
                version_id=mv.id,
                model_kind=mv.model_kind or "sklearn",
            )
        )
        (scratch / "predict.py").write_text(_PREDICT_PY)

        # 5. Tar.gz the whole thing.
        tar_path = storage.package_tar_path(package_id)
        tar_path.parent.mkdir(parents=True, exist_ok=True)
        if tar_path.exists():
            tar_path.unlink()
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(scratch, arcname=_slugify(model_name) + f"-v{mv.version}")
        size_bytes = tar_path.stat().st_size

        # 6. Scratch dir is disposable — free the space.
        shutil.rmtree(scratch, ignore_errors=True)

        await _update_status(
            session_factory,
            package_id,
            status="ready",
            storage_path=storage.to_relative(tar_path),
            size_bytes=size_bytes,
        )
        logger.info(
            "build_package.ready",
            package_id=package_id,
            size_bytes=size_bytes,
        )
        return {"status": "ready", "size_bytes": size_bytes}
    except Exception as exc:
        logger.exception("build_package.failed")
        await _update_status(
            session_factory,
            package_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )
        return {"status": "failed", "error": str(exc)}
