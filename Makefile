# aiochainscan — agent-friendly task runner (`make help`)
# Quality targets mirror the (temporarily disabled) GitHub CI lint/test jobs,
# so `make ci-local` is the source of truth while Actions is off.

.DEFAULT_GOAL := help

# Colors
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

UV := $(shell command -v uv 2> /dev/null)
RUN := $(if $(UV),uv run,)
SYNC := $(if $(UV),uv sync --extra dev --frozen,pip install -e ".[dev]")

.PHONY: help install-dev fastabi lint format format-check typecheck import-lint \
	pre-commit test test-fast test-slow ci-local preflight validate commit \
	wt-new wt-rm wt-ls ci-watch clean

##@ Setup

install-dev: ## Install dev dependencies (uv sync --extra dev --frozen)
	$(SYNC)
	@echo "$(GREEN)✅ Development environment ready$(RESET)"

fastabi: ## Build the Rust FFI (maturin develop --release; needs Rust toolchain)
	cd aiochainscan/fastabi && $(if $(UV),uv run --extra fast,) maturin develop --release
	@echo "$(GREEN)✅ fastabi built$(RESET)"

##@ Quality (mirrors disabled GitHub CI)

lint: ## Ruff lint
	$(RUN) ruff check .

format: ## Ruff format (auto-fix)
	$(RUN) ruff format .

format-check: ## Ruff format (check only)
	$(RUN) ruff format --check .

typecheck: ## mypy --strict aiochainscan
	$(RUN) mypy --strict aiochainscan

import-lint: ## Import Linter (hexagonal dependency rule)
	$(RUN) lint-imports --config .importlinter

pre-commit: ## pre-commit run --all-files
	$(RUN) pre-commit run --all-files --show-diff-on-failure

test: ## pytest (unit suite; benchmarks/slow deselected via pyproject)
	$(RUN) pytest tests/ -q --tb=short

test-fast: ## pytest fail-fast (stop on first failure)
	$(RUN) pytest tests/ -q -x --tb=short

test-slow: ## pytest including slow/integration-marked tests
	$(RUN) pytest tests/ -q -m "" --tb=short

ci-local: lint format-check import-lint typecheck test ## Full local CI mirror — run instead of GitHub Actions while it is disabled
	@echo "$(GREEN)✅ Local CI mirror passed (lint, format, import-lint, mypy, pytest)$(RESET)"

##@ Agent workflow (scripts/agent/)

preflight: ## Environment preflight — run BEFORE starting a task
	./scripts/agent/preflight.sh

validate: ## The DONE gate — run BEFORE claiming a task finished
	./scripts/agent/validate_fast.sh

commit: ## Safe commit with index.lock retry: make commit MSG="..." PATHS="f1 f2"
	@test -n "$(MSG)" || { echo 'Usage: make commit MSG="commit message" PATHS="file1 file2"' >&2; exit 1; }
	./scripts/agent/safe_commit.sh -m "$(MSG)" $(PATHS)

wt-new: ## New agent worktree: make wt-new SLUG=my-task [TYPE=feat] [BASE=origin/main]
	@test -n "$(SLUG)" || { echo 'Usage: make wt-new SLUG=my-task [TYPE=feat] [BASE=origin/main]' >&2; exit 1; }
	./scripts/agent/new-worktree.sh $(SLUG) $(TYPE) $(BASE)

wt-rm: ## Teardown worktree: make wt-rm SLUG=my-task ARGS="--yes"
	./scripts/agent/rm-worktree.sh $(SLUG) $(ARGS)

wt-ls: ## List worktrees + merge status (dry-run)
	./scripts/agent/rm-worktree.sh

ci-watch: ## Watch GitHub Actions run for current branch (CI currently disabled → exit 4)
	./scripts/agent/ci_watch.sh

##@ Utilities

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
	@echo "$(GREEN)✅ Cleaned$(RESET)"

help: ## Show this help
	@echo "$(BLUE)aiochainscan$(RESET) - Available commands:\n"
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-14s$(RESET) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(RESET)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
