# AIpacken — Self-Hosted AI Platform

A local, Docker-based AI platform. Upload a dataset, pick a model (including AutoGluon, zero-config), train, inspect metrics / SHAP / bias, and deploy to a live API — all from a single web UI, running entirely on your machine.

## Stack

- **Backend**: FastAPI + Arq (async worker) + SQLAlchemy + Alembic + Postgres 16
- **Storage**: one named Docker volume (`platform-data`) — datasets, artifacts, models, reports all live on the local filesystem
- **Reverse proxy**: Traefik v3 (dynamic routing to per-model serving containers)
- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS (wired to AIpacken design tokens)
- **Infra**: Docker Compose (v0). Kubernetes-ready topology (v2).

No cloud SDKs. No S3 protocol in the critical path. No external tracking server. What the frontend renders, the backend produces directly from Postgres + the local volume.

## Quick start

```bash
cp .env.example .env
# edit .env — set PLATFORM_SECRET_KEY and PLATFORM_ADMIN_PASSWORD

make dev          # brings up the full stack with hot reload
# → http://localhost           (frontend)
# → http://localhost/api/healthz   (api health)
```

Stop with `make down`. Wipe volumes (including the `platform-data` volume) with `make clean`.

## Repo layout

```
apps/
  api/             FastAPI + Arq worker + builder (same image, different entrypoints)
  web/             Vite + React SPA
packages/
  api-spec/        committed openapi.json
  api-client/      generated TS types
infra/
  compose/         docker-compose.yml (base + dev overlays)
  templates/       Jinja2 Dockerfiles for per-run trainer / serving images
  traefik/         dynamic proxy config
trainer_base/      platform/trainer-base image — generic training entrypoint
serving_base/      platform/serving-base image — generic FastAPI serving app
scripts/           bootstrap.sh, build_bases.sh
```

## Storage layout

Everything produced by the platform lives on the `platform-data` named Docker volume, mounted at `/var/platform-data` inside `api`, `worker`, and `builder`:

```
/var/platform-data/
├── datasets/{dataset_id}/raw/<filename>
├── datasets/{dataset_id}/profile.json
├── runs/{run_id}/
│   ├── metrics.jsonl                 # trainer writes; worker reads on exit
│   ├── artifacts/                    # model.pkl, shap_global.png, bias.png, ...
│   └── reports/{shap.json, bias.json}
└── models/{model_version_id}/model.pkl
```

## Design system

The frontend follows the **AIpacken** design system, shipped in `DESIGN.zip` and extracted into `apps/web/src/styles/` + `apps/web/public/`. Teal-on-white, Plus Jakarta Sans + Inter + Lora, glass-card surfaces with a subtle teal glow. Voice: calm competence, no marketing gloss, CTAs end with `→`.

## Status

**v0** — lean MVP end-to-end: upload → profile → built-in models (sklearn logistic, sklearn gradient boosting, xgboost, lightgbm, AutoGluon) → train → SHAP + fairlearn bias → deploy → realtime API.

**v1 (next)** — custom PyPi packages (pinned allowlist), batch prediction, run comparison, prediction browser, disk-pressure janitor.

**v2 (later)** — Kubernetes topology, OIDC/SSO, per-user quotas.

## License

See `LICENSE`.
