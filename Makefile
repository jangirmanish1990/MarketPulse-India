# MarketPulse India — top-level Makefile
# All canonical workflows go through these targets. CI runs the same targets.

PY        := python
UV        := uv
RUFF      := ruff
MYPY      := mypy
PYTEST    := pytest
ALEMBIC   := alembic
COMPOSE   := docker compose

# ---------------------------------------------------------------------------
.PHONY: help
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_.-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
.PHONY: install
install:  ## Install all deps (dev + evals) into the current venv
	$(UV) sync --extra dev --extra evals --extra infra || \
	  $(PY) -m pip install -e ".[dev,evals,infra]"

.PHONY: install-prod
install-prod:  ## Install runtime deps only
	$(UV) sync || $(PY) -m pip install -e "."

# ---------------------------------------------------------------------------
.PHONY: dev
dev:  ## Run local dev stack (api + db + redis) via docker compose
	$(COMPOSE) up --build

.PHONY: dev-bg
dev-bg:  ## Run local dev stack detached
	$(COMPOSE) up -d --build

.PHONY: dev-down
dev-down:  ## Stop local dev stack
	$(COMPOSE) down

.PHONY: api
api:  ## Run FastAPI directly (no docker), expects local pg + redis
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
.PHONY: lint
lint:  ## Run ruff format + check and mypy strict
	$(RUFF) format .
	$(RUFF) check --fix .
	$(MYPY) backend agents mcp_servers lambdas

.PHONY: lint-check
lint-check:  ## Lint without auto-fix (for CI)
	$(RUFF) format --check .
	$(RUFF) check .
	$(MYPY) backend agents mcp_servers lambdas

# ---------------------------------------------------------------------------
.PHONY: test
test:  ## Run unit tests (excludes evals + e2e)
	$(PYTEST) -q -m "not evals and not e2e"

.PHONY: test-all
test-all:  ## Run everything including evals + e2e
	$(PYTEST) -q

.PHONY: evals
evals:  ## Run only the LLM eval suite
	$(PYTEST) -q -m evals tests/evals/

.PHONY: e2e
e2e:  ## Run only end-to-end tests
	$(PYTEST) -q -m e2e tests/e2e/

# ---------------------------------------------------------------------------
.PHONY: migrate
migrate:  ## Apply pending Alembic migrations to local DB
	$(ALEMBIC) upgrade head

.PHONY: migration
migration:  ## Generate a new Alembic migration. Usage: make migration m="add foo"
	$(ALEMBIC) revision --autogenerate -m "$(m)"

.PHONY: downgrade
downgrade:  ## Roll back the most recent migration on local DB
	$(ALEMBIC) downgrade -1

# ---------------------------------------------------------------------------
.PHONY: seed
seed:  ## Seed local DB with NIFTY50 + 365 days of bars
	$(PY) scripts/seed_corpus.py --universe NIFTY50 --days 365

# ---------------------------------------------------------------------------
.PHONY: deploy
deploy:  ## Deploy to AWS. Usage: make deploy env=dev|staging|prod
	@if [ -z "$(env)" ]; then echo "Usage: make deploy env=dev|staging|prod"; exit 1; fi
	@echo ">>> Deploying to $(env). Run /deploy-aws inside Claude Code for the guarded flow."
	bash scripts/deploy.sh $(env)

# ---------------------------------------------------------------------------
.PHONY: clean
clean:  ## Remove caches and build artifacts
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -prune -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -prune -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -prune -exec rm -rf {} +
	rm -rf dist build *.egg-info
