# AIpacken — Self-Hosted AI Platform

A local, Docker-based AI platform. Upload a dataset, pick a model (including AutoGluon, zero-config), train, inspect metrics / SHAP / bias, and deploy to a live API — all from a single web UI, running entirely on your machine.

> Origin: this repo started as the AWS-SageMaker [MLOps template](https://aws.amazon.com/blogs/machine-learning/deploy-an-mlops-solution-that-hosts-your-model-endpoints-in-aws-lambda/). It has been ported to a self-hosted architecture — SageMaker, Lambda, CodePipeline, and CDK are all gone.

## Stack

- **Backend**: FastAPI + Arq (async worker) + SQLAlchemy + Alembic + Postgres 16
- **Object store**: MinIO (S3-compatible)
- **Experiment tracking / model registry**: MLflow
- **Reverse proxy**: Traefik v3 (dynamic routing to per-model serving containers)
- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS (wired to AIpacken design tokens)
- **Infra**: Docker Compose (v0). Kubernetes-ready topology (v2).

## Quick start

```bash
cp .env.example .env
# edit .env — set PLATFORM_SECRET_KEY and PLATFORM_ADMIN_PASSWORD

make dev          # brings up the full stack with hot reload
# → http://localhost           (frontend)
# → http://localhost/api/healthz   (api health)
# → http://localhost/mlflow    (mlflow ui)
```

Stop with `make down`. Wipe volumes with `make clean`.

## Repo layout

```
apps/
  api/             FastAPI + Arq worker (same image, different entrypoints)
  web/             Vite + React SPA
packages/
  api-spec/        committed openapi.json (drift-checked in CI)
  api-client/      generated TS types
infra/
  compose/         docker-compose.yml (base + dev + obs overlays)
  templates/       Jinja2 Dockerfiles for per-run trainer / serving images
  traefik/         static + dynamic proxy config
  postgres/        init.sql
trainer_base/      platform/trainer-base image — generic training entrypoint
serving_base/      platform/serving-base image — generic FastAPI serving app
scripts/           bootstrap.sh, build_bases.sh
```

## Design system

The frontend follows the **AIpacken** design system, shipped in `DESIGN.zip` and extracted into `apps/web/src/styles/` + `apps/web/public/`. Teal-on-white, Plus Jakarta Sans + Inter + Lora, glass-card surfaces with a subtle teal glow. Voice: calm competence, no marketing gloss, CTAs end with `→`.

## Status

**v0 (in progress)** — lean MVP end-to-end: upload → profile → built-in models (sklearn logistic, sklearn gradient boosting, AutoGluon) → train → SHAP + fairlearn bias → deploy → realtime API.

**v1 (next)** — custom PyPi packages (pinned allowlist), batch prediction, run comparison, prediction browser.

**v2 (later)** — Kubernetes topology, OIDC/SSO, per-user quotas.

## License

See `LICENSE`.
