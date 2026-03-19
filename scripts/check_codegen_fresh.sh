#!/usr/bin/env bash
# Check that generated JSON Schema and TS types are up to date.
# Exits 1 if regeneration produces different output.
set -euo pipefail

echo "Regenerating schemas..."
uv run python scripts/generate_jsonschema.py > /dev/null
node scripts/generate_ts_types.mjs > /dev/null

if git diff --quiet packages/schemas/jsonschema packages/schemas/ts/src; then
  echo "Codegen is fresh."
else
  echo "ERROR: Generated schemas are stale. Run 'make codegen' and commit."
  git diff --stat packages/schemas/jsonschema packages/schemas/ts/src
  exit 1
fi
