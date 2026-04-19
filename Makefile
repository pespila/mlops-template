COMPOSE_BASE := infra/compose/docker-compose.yml
COMPOSE_DEV  := infra/compose/docker-compose.dev.yml
ENV_FILE     := .env

# Resolve a `docker` binary even if Docker Desktop's CLI wasn't symlinked into PATH.
DOCKER := $(shell \
  command -v docker 2>/dev/null \
  || ( [ -x /Applications/Docker.app/Contents/Resources/bin/docker ] \
       && echo /Applications/Docker.app/Contents/Resources/bin/docker ) \
  || ( [ -x /usr/local/bin/docker ] && echo /usr/local/bin/docker ) \
  || ( [ -x $(HOME)/.docker/bin/docker ] && echo $(HOME)/.docker/bin/docker ) \
)

ifeq ($(DOCKER),)
  $(error docker not found; install Docker Desktop or add it to your PATH)
endif

# Docker Desktop ships credential helpers (docker-credential-desktop) and
# buildx / compose plugins next to the `docker` binary. Prepend that directory
# to PATH so `docker compose pull` can find them.
DOCKER_BIN_DIR := $(dir $(DOCKER))
export PATH := $(DOCKER_BIN_DIR):$(PATH)

COMPOSE      := $(DOCKER) compose --env-file $(ENV_FILE) -f $(COMPOSE_BASE)
COMPOSE_DEV_CMD := $(DOCKER) compose --env-file $(ENV_FILE) -f $(COMPOSE_BASE) -f $(COMPOSE_DEV)

.PHONY: help
help:
	@echo "Targets:"
	@echo "  make dev          - Bring up the full stack with hot reload"
	@echo "  make up           - Bring up the stack (production-like)"
	@echo "  make down         - Stop the stack"
	@echo "  make clean        - Stop the stack AND drop volumes"
	@echo "  make logs         - Tail all container logs"
	@echo "  make seed         - Seed a demo dataset into MinIO"
	@echo "  make test         - Run pytest + vitest"
	@echo "  make test-e2e     - Run Playwright end-to-end tests"
	@echo "  make lint         - Run ruff + eslint"
	@echo "  make fmt          - Format code (ruff format + prettier)"
	@echo "  make openapi      - Regenerate packages/api-spec/openapi.json"
	@echo "  make build-bases  - Build trainer_base and serving_base images"
	@echo "  make config       - Validate docker compose config"

.env:
	@echo "[bootstrap] creating .env from .env.example"
	@cp .env.example .env
	@SECRET=$$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))'); \
	  sed -i.bak "s|PLATFORM_SECRET_KEY=.*|PLATFORM_SECRET_KEY=$$SECRET|" .env && rm .env.bak
	@TOKEN=$$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))'); \
	  sed -i.bak "s|INTERNAL_HMAC_TOKEN=.*|INTERNAL_HMAC_TOKEN=$$TOKEN|" .env && rm .env.bak
	@echo "[bootstrap] .env created. Review and edit PLATFORM_ADMIN_PASSWORD before exposing."

.PHONY: dev
dev: .env
	$(COMPOSE_DEV_CMD) up --build

.PHONY: up
up: .env
	$(COMPOSE) up -d --build

.PHONY: down
down:
	$(COMPOSE_DEV_CMD) down

.PHONY: clean
clean:
	$(COMPOSE_DEV_CMD) down -v

.PHONY: logs
logs:
	$(COMPOSE) logs -f

.PHONY: config
config: .env
	$(COMPOSE) config --quiet && echo "docker compose config OK"

.PHONY: seed
seed:
	$(COMPOSE) exec api python -m aipacken.scripts.seed_demo

.PHONY: test
test:
	$(COMPOSE) exec -T api pytest -q
	cd apps/web && pnpm test --run

.PHONY: test-e2e
test-e2e:
	cd apps/web && pnpm test:e2e

.PHONY: lint
lint:
	$(COMPOSE) exec -T api ruff check .
	cd apps/web && pnpm lint

.PHONY: fmt
fmt:
	$(COMPOSE) exec -T api ruff format .
	$(COMPOSE) exec -T api ruff check --fix .
	cd apps/web && pnpm fmt

.PHONY: openapi
openapi:
	$(COMPOSE) exec -T api python -m aipacken.scripts.export_openapi > packages/api-spec/openapi.json
	cd apps/web && pnpm gen:api

.PHONY: build-bases
build-bases:
	docker build -t platform/trainer-base:latest trainer_base/
	docker build -t platform/serving-base:latest serving_base/
