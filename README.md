# AIpacken — Self-Hosted AI Platform

A local, Docker-based MLOps platform. Upload a dataset, pick a model
(34 built-in catalog entries across classification, regression,
clustering, forecasting, and recommendation — plus AutoGluon), train,
inspect metrics / SHAP / bias, promote a version, and deploy to a live
API — all from a single web UI, running entirely on your machine.

## Stack

- **Backend**: FastAPI + Arq (async worker, fast/slow queue split) + SQLAlchemy 2 + Alembic + Postgres 16
- **Tracking & registry**: MLflow 2.17 (experiments, metrics, artifacts, model registry with aliases)
- **Object store**: MinIO (S3-compatible, local-only). MLflow writes artifacts through its proxied-artifact endpoint; clients never speak S3 directly.
- **Reverse proxy**: Traefik v3 (dynamic routing to per-model serving containers, file-provider watched)
- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS (AIpacken design tokens)
- **Infra**: Docker Compose. Kubernetes-ready topology planned.

MLflow is the source of truth for experiment metadata, metrics, and
the model registry. The platform DB owns sessions/tenancy, datasets,
deployments (plus a snapshot of the MLflow version they pin), and
prediction audit rows. Frontend renders everything through the
platform API; it never talks to MLflow directly.

## Quick start

```bash
cp .env.example .env
# edit .env — rotate PLATFORM_SECRET_KEY, PLATFORM_ADMIN_PASSWORD,
# INTERNAL_HMAC_TOKEN, MINIO_ROOT_PASSWORD, AWS_SECRET_ACCESS_KEY.

make dev          # brings up the full stack with hot reload
# → http://localhost           (frontend)
# → http://localhost/api/healthz   (api health)
```

Stop with `make down`. Wipe volumes (including `platform-data`,
`pgdata`, and MinIO's `mlflow-artifacts` bucket) with `make clean`.

## Repo layout

```
apps/
  api/             FastAPI + Arq worker + builder (same image, different entrypoints)
  web/             Vite + React SPA
packages/
  api-spec/        committed openapi.json (drift-guarded in CI)
  api-client/      generated TS types
infra/
  compose/         docker-compose.yml (base + dev overlay)
  mlflow/          custom MLflow image (boto3 + psycopg2 pre-installed)
  postgres/        one-shot init scripts (MLflow schema + platform schema)
  traefik/         dynamic per-deployment routes
trainer_base/      platform/trainer-base image — generic training entrypoint
serving_base/      platform/serving-base image — generic FastAPI serving app
scripts/           backup.sh, restore.sh
```

## Storage layout

The named `platform-data` Docker volume carries everything the
platform produces on the filesystem:

```
/var/platform-data/
├── datasets/{dataset_id}/raw/<filename>     uploaded CSV/Parquet
├── datasets/{dataset_id}/profile.json
├── runs/{run_id}/logs.jsonl                 trainer stdout/stderr (SSE tail)
├── deployments/{deployment_id}/             MLflow artifacts staged read-only
│   └── artifacts/model.pkl + .sig + input_schema.json
└── packages/{package_id}.tar.gz             downloadable deployment bundle
```

Heavy MLflow-owned artifacts (`model.pkl`, `reports/shap.json`,
`reports/bias.json`, `metrics.jsonl`, PNG plots) live in MinIO under
the `mlflow-artifacts` bucket. The serving worker pulls them down into
`deployments/{id}/` on first deploy so the serving container loads
from a local bind-mount without a live MLflow dependency.

## Design system

The frontend follows the **AIpacken** design system in
`apps/web/src/styles/` + `apps/web/public/`. Teal-on-white, Plus
Jakarta Sans + Inter + Lora, glass-card surfaces with a subtle teal
glow. Voice: calm competence, no marketing gloss, CTAs end with `→`.

## Status

**v0 (current)** — end-to-end: upload → profile → train (HPO-optional,
honest held-out test metrics) → MLflow-tracked metrics + SHAP +
fairlearn bias → registry with `@staging` / `@production` aliases →
deploy → realtime API → downloadable package.

**v1 (next)** — custom PyPi packages (pinned allowlist), batch
prediction, run comparison, prediction browser, disk-pressure janitor.

**v2 (later)** — Kubernetes topology, OIDC/SSO, per-user quotas.

## Security posture

- Session cookies, argon2id passwords (bcrypt verify-fallback for
  historical hashes).
- HMAC-signed pickles: every `model.pkl` carries a `.sig`, verified
  before `joblib.load` in the serving container.
- docker-socket-proxy fronts the builder so per-job containers can
  start without exposing `/var/run/docker.sock` to the api.
- Tenant authz walks Run → Experiment.user_id; admins bypass.
- `/api/internal/mlflow/*` diagnostics are admin-gated.

## Operations

- `scripts/backup.sh` — pg_dump + platform-data snapshot into a dated tarball.
- `scripts/restore.sh` — restore from a backup tarball (idempotent).
- Migration 0008 (MLflow cutover phase B) is destructive; set
  `AIPACKEN_ALLOW_DESTRUCTIVE_MIGRATION=1` and take a backup before
  running `alembic upgrade head` on a populated DB.

## License

See `LICENSE`.
