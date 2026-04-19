COMPOSE_BASE := infra/compose/docker-compose.yml
COMPOSE_DEV  := infra/compose/docker-compose.dev.yml
ENV_FILE     := .env
COMPOSE      := docker compose --env-file $(ENV_FILE) -f $(COMPOSE_BASE)
COMPOSE_DEV_CMD := docker compose --env-file $(ENV_FILE) -f $(COMPOSE_BASE) -f $(COMPOSE_DEV)

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

.PHONY: dev
dev:
	$(COMPOSE_DEV_CMD) up --build

.PHONY: up
up:
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
config:
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
