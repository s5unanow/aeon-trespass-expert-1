.PHONY: help bootstrap lint format typecheck test codegen export clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

bootstrap: ## Install all deps (uv sync + pnpm install)
	uv sync
	pnpm install

lint: ## Run ruff check + ruff format --check + mypy + import-linter + file-length + pnpm lint
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy apps/pipeline/src packages/schemas/python
	uv run lint-imports
	uv run python scripts/check_file_length.py
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

export: ## Export pipeline artifacts to web public (re-generates apps/web/public/documents/)
	uv run python scripts/export_to_web.py

export-en: ## Export EN-only extraction artifacts for review
	uv run python scripts/export_to_web.py --edition en

codegen: ## Regenerate JSON Schema + TS types from Pydantic models
	uv run python scripts/generate_jsonschema.py
	node scripts/generate_ts_types.mjs

clean: ## Remove caches and build artifacts
	rm -rf artifacts/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
