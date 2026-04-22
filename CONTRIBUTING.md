# Contributing to AIpacken

Thanks for your interest in making AIpacken better. This guide covers how to
set up a local stack, how to make changes, and the expectations for a clean
pull request.

## Project layout

- `apps/api/` — FastAPI REST backend, Arq async worker, Docker builder service (Python 3.11)
- `apps/web/` — React 18 + Vite + TypeScript SPA
- `trainer_base/` — generic training container image (sklearn, XGBoost, LightGBM, AutoGluon)
- `serving_base/` — per-model FastAPI serving container image
- `infra/compose/` — Docker Compose orchestration
- `infra/traefik/` — reverse proxy + dynamic model routing
- `packages/api-spec/` — OpenAPI schema consumed by the web client

See `docs/` for deeper docs (architecture, runbooks) as they land.

## Prerequisites

- Docker Desktop (or Docker Engine ≥ 24) with Compose v2
- `pnpm` (for local web work outside containers; the dev overlay runs it inside)
- `python3.11` (for local API tooling outside containers; optional)
- `make`

## One-time setup

```bash
git clone <this-repo>
cd mlops-template
make .env          # generates .env with a random PLATFORM_SECRET_KEY and INTERNAL_HMAC_TOKEN
```

Review `.env` before exposing the stack to anything beyond `localhost`. In
particular, set a real `PLATFORM_ADMIN_PASSWORD` — the stack refuses to boot
with `PLATFORM_ENV=prod` if any secret still carries a `change-me*`
placeholder.

## Development loop

Bring up the full stack with hot reload:

```bash
make dev           # builds trainer/serving base images on first run, then starts compose
```

Iterate:

- Backend changes hot-reload via uvicorn (watchfiles)
- Web changes hot-reload via Vite on `http://localhost`
- Worker changes require `docker compose restart worker`
- Trainer/serving base image changes require `make build-bases`

Common targets:

```bash
make down          # stop the stack
make clean         # stop AND drop volumes (wipes platform-data + postgres)
make logs          # tail all container logs
make seed          # seed demo datasets onto the platform-data volume
make openapi       # regenerate packages/api-spec/openapi.json + web client types
```

## Testing and quality gates

```bash
make test          # pytest (apps/api) + vitest (apps/web) — requires running stack
make test-e2e      # Playwright against the running stack (once e2e specs exist)
make lint          # ruff check (api) + eslint (web)
make fmt           # ruff format + ruff --fix (api) + prettier (web)
make config        # validate docker compose config
```

A PR should not land with `make lint` or `make test` failing on the author's
machine. CI will re-verify once it exists.

## Branches and commits

- Branch from `main`. Prefix by intent: `feat/…`, `fix/…`, `chore/…`, `docs/…`.
- One logical change per commit. Commit messages follow this repo's
  established style: a short imperative subject line, then a blank line, then
  a body explaining the *why* and any trade-offs.
- Reference the code review in `docs/review/CODE_REVIEW_REPORT.md` by Top-10
  number or per-area P0/P1/P2 anchor when your change addresses it.

## Pull request checklist

- [ ] `make lint` passes
- [ ] `make test` passes (or explicitly document why not)
- [ ] New behaviour is covered by a test (unit or integration; see `apps/api/tests/` and `apps/web/src/**/*.test.tsx`)
- [ ] No secrets, `.env` files, cookies, or build artifacts added to the commit
- [ ] If the OpenAPI contract changed: `make openapi` was re-run and the diff is committed
- [ ] If a new env var was added: `.env.example` and the Pydantic `Settings` model are both updated
- [ ] Documentation / README / relevant runbook is updated when behaviour that a consumer relies on changes

## Security issues

Do **not** open a public GitHub issue for security vulnerabilities. Report
them privately to the maintainers (see `README.md` for the current contact
address). Include: reproduction steps, affected endpoints or components, and
the expected impact. We will acknowledge within three working days.

## Code of Conduct

Participation in this project is subject to the project's Code of Conduct
(see `CODE_OF_CONDUCT.md` when published). In short: be respectful, assume
good intent, critique ideas not people, and prefer written clarity over
speed.
