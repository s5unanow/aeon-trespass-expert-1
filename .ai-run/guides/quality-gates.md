# Quality Gates

Exact commands for every gate, ordered fastest to slowest. Makefile targets are the canonical invocation surface (`Makefile` is the source of truth; the gate enumeration and counts live in `CLAUDE.md` § Quality gates, which is CI-parsed — do not restate counts here).

Two tiers: **local** (pre-commit hook runs a fast subset automatically on `git commit` via `.claude/hooks/pre-commit-check.sh`) and **CI** (GitHub Actions on every PR/push; includes everything local plus base-branch-comparison and rendering checks). Local green is necessary but not sufficient — merge requires CI green.

### Format check

**Run**: `uv run ruff format --check .` (Python) and `cd apps/web && pnpm exec prettier --check "src/**/*.{ts,tsx,css}"` (web)
**Pass**: no output / "N files already formatted", exit 0.
**Fail**: lists files that would be reformatted — formatting drift.
**Auto-fix**: `make format`

### Lint (aggregate)

**Run**: `make lint`
**Pass**: each sub-check prints OK; exit 0. Covers ruff check, ruff format --check, mypy, import-linter layer contracts, file-length cap, fixture manifest, instruction-drift, make/doc parity, codegen freshness, and `pnpm lint` (oxlint).
**Fail**: first failing sub-check prints its violation (e.g. ruff rule code, import-linter broken contract, `check_instruction_drift` drift message) and exits non-zero.
**Auto-fix**: `make format` fixes formatting only; other findings need code changes.

### Type-check

**Run**: `make typecheck`
**Pass**: `mypy` reports "Success: no issues" and `tsc --noEmit` exits silently.
**Fail**: `error:` lines with file:line — type errors block commit (mypy runs `--strict`).

### Fast test subset (what the pre-commit hook runs)

**Run**: `uv run pytest -x -q --timeout=60 -m "not slow"`
**Pass**: `N passed` within the 60s-per-test timeout.
**Fail**: first failure aborts (`-x`); a timeout means a test exceeded 60s and should be marked `@pytest.mark.slow` or fixed.
**Skip if**: never skip silently — this is the commit gate.

### Full test suite

**Run**: `make test`
**Pass**: full pytest suite (including `slow`-marked tests, no timeout) and `pnpm -r run test` (vitest) all green.
**Fail**: standard pytest/vitest failure output; CI runs this form, so a local fast-subset pass can still fail here.

### Codegen freshness

**Run**: `make check-codegen`
**Pass**: generated JSON Schema + TS types under `packages/schemas/` match the Pydantic sources.
**Fail**: diff between committed and regenerated output — run `make codegen` and commit the result. Never hand-edit generated dirs (`.claude/rules/schemas.md`).
**Skip if**: no Pydantic model changed (CI still verifies).

### Fixture manifest

**Run**: `make validate-fixtures`
**Pass**: manifest and annotation metadata validate.
**Fail**: names the fixture entry that drifted from the manifest.

### Visual regression (web rendering changes only)

**Run**: `cd apps/web && pnpm test:e2e` (CI job `visual-regression / visual` is authoritative — baselines are captured on Linux; local macOS runs drift 2–4% and may exceed the 0.005 threshold, see `.claude/rules/visual-verify.md` § Platform note)
**Pass**: all `toHaveScreenshot` assertions within `maxDiffPixelRatio: 0.005` (`apps/web/playwright.config.ts`).
**Fail**: pixel diff beyond threshold. If the change is intentional, refresh baselines locally with `pnpm --filter @atr/web run test:visual:update` in a dedicated commit; CI never regenerates baselines.
**Skip if**: change touches no rendering surface (docs/pipeline-internal only).

### Aggregate — definition of done (local)

**Run**: `make check`
**Pass**: `lint + typecheck + test` all green — the canonical local definition of done (`Makefile` `check` target).
**Fail**: whichever sub-target failed; fix and re-run. Then push and confirm CI green (`gh pr checks <pr> --watch`) — the full CI gate set (see `CLAUDE.md` § Quality gates) is what "Done" means.
