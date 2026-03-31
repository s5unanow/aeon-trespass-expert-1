.PHONY: help bootstrap lint format typecheck test test-hooks codegen check-codegen export clean validate-fixtures config-health erosion-report

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

bootstrap: ## Install all deps (uv sync + pnpm install)
	uv sync
	pnpm install

lint: ## Run ruff check + ruff format --check + mypy + import-linter + file-length + fixtures + codegen freshness + pnpm lint
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy apps/pipeline/src packages/schemas/python
	uv run lint-imports
	uv run python scripts/check_file_length.py
	uv run python scripts/validate_fixture_manifest.py
	bash scripts/check_codegen_fresh.sh
	pnpm -r run lint

format: ## Auto-fix formatting
	uv run ruff format .
	uv run ruff check --fix .
	pnpm -r run format

typecheck: ## Run mypy + tsc
	uv run mypy apps/pipeline/src packages/schemas/python
	pnpm -r run typecheck

test: ## Run all tests (pytest + pnpm test)
	uv run pytest
	pnpm -r run test

test-hooks: ## Run hook integration tests (fast, no external deps)
	uv run pytest apps/pipeline/tests/integration/test_hooks.py -v --timeout=10

export: ## Export pipeline artifacts to web public (re-generates apps/web/public/documents/)
	uv run python scripts/export_to_web.py

export-en: ## Export EN-only extraction artifacts for review
	uv run python scripts/export_to_web.py --edition en

check-codegen: ## Check that generated schemas match Pydantic sources (requires pnpm install)
	@command -v node >/dev/null 2>&1 || { echo "ERROR: node not found. Run 'make bootstrap' first."; exit 1; }
	@test -d node_modules/.pnpm || { echo "ERROR: pnpm packages not installed. Run 'pnpm install' first."; exit 1; }
	bash scripts/check_codegen_fresh.sh

codegen: ## Regenerate JSON Schema + TS types from Pydantic models
	uv run python scripts/generate_jsonschema.py
	node scripts/generate_ts_types.mjs

validate-fixtures: ## Validate fixture manifest and annotation metadata
	uv run python scripts/validate_fixture_manifest.py

config-health: ## Check config drift across CLAUDE.md, hooks, skills, and CI
	uv run python scripts/check_config_health.py

erosion-report: ## Advisory code erosion report (non-blocking)
	uv run python scripts/check_code_erosion.py --base main --head HEAD

clean: ## Remove caches and build artifacts
	rm -rf artifacts/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
