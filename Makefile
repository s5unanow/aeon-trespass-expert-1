.PHONY: lint test codegen typecheck format clean install

install:
	uv sync
	pnpm install

lint:
	uv run ruff check .
	uv run mypy apps/pipeline/src packages/schemas/python
	pnpm -r run lint

format:
	uv run ruff format .
	uv run ruff check --fix .
	pnpm -r run format

test:
	uv run pytest
	pnpm -r run test

codegen:
	uv run python scripts/generate_jsonschema.py
	node scripts/generate_ts_types.mjs

typecheck:
	uv run mypy apps/pipeline/src packages/schemas/python
	pnpm -r run typecheck

clean:
	rm -rf artifacts/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
