# CLAUDE.md

**Purpose**: Claude Code entrypoint for `aeon-trespass-expert`. Canonical repo guidance lives in `AGENTS.md`; the sections below the import are CI-parsed anchors, not general guidance.

<!-- ai-run-init:guide-imports start -->
@AGENTS.md
<!-- ai-run-init:guide-imports end -->

---

## CI-parsed anchors

> The sections below are parsed by fail-closed repo guards that anchor on `CLAUDE.md` specifically — `scripts/check_make_doc_parity.py` (the `make lint` one-line summary) and `scripts/check_instruction_drift.py` (the CI gate enumeration and the canonical safety-gate-scope parenthetical). They must stay in this file, verbatim, until those guards are retargeted. Everything else lives in `AGENTS.md` and `.ai-run/guides/`.

## Commands

```bash
make bootstrap                # Install all deps (uv sync + pnpm install)
make lint                     # ruff check + ruff format --check + mypy + import-linter + file-length + fixture-manifest + instruction-drift + make/doc parity + codegen freshness + pnpm lint
make check                    # Aggregate: lint + typecheck + test (the canonical local "definition of done")
make typecheck test codegen   # mypy + tsc / all tests / regenerate JSON Schema + TS types from Pydantic
make check-codegen            # Verify generated schemas match Pydantic sources
make verify-branch-protection # Audit live main branch protection against workflow policy
make export format clean      # Export to web public / auto-fix formatting / remove caches
```

## Quality gates

Two tiers of checks run at different stages. Both must pass.

### Local (pre-commit hook, 9 checks: 1 secret guard + 8 quality gates) — runs on `git commit` via `.claude/hooks/pre-commit-check.sh`, <60 s target

0. `secret guard` — blocks staged secrets (filenames: `.env`, `*.key`, `*.pem`, `credentials.json`; content: `sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers)
1. `ruff check` — lint (includes McCabe complexity C901, max 12)
2. `ruff format --check` — format violations
3. `mypy --strict` — type errors
4. `lint-imports` — import layer contracts (no cyclic dependencies)
5. `check_file_length.py` — max 400 lines per source and test file (pre-existing violators grandfathered in `KNOWN_VIOLATORS` and must not grow)
6. `oxlint` — frontend lint (`import/no-cycle`, `max-lines: 400`)
7. `tsc --noEmit` — frontend type check
8. `pytest -x -q --timeout=60 -m "not slow"` — fast test subset only

### CI (GitHub Actions, 9 + 9 extra) — runs on every push to `main` and every PR; includes all 9 local gates plus:

9. `check_codegen_fresh.sh` — generated JSON Schema + TS types match Pydantic sources (also `make check-codegen`).
10. `validate_fixture_manifest.py` — fixture integrity (also `make validate-fixtures`).
11. `check_extraction_scope.py` — CI-only (needs base-branch comparison); reports when a PR touches extraction scope.
12. `check_golden_refresh.py` — CI-only (needs base-branch comparison); gates golden refreshes when extraction scope is detected.
13. `visual-regression / visual` — Playwright `toHaveScreenshot` at `maxDiffPixelRatio: 0.005`. Full stack in `.claude/rules/visual-verify.md` § "Visual regression CI gate".
14. `visual-gate-scope / scan` — content-derived scan of workflow YAML and `apps/web/package.json` for flags that bypass the visual-regression gate. See `.claude/rules/guards.md` Rule G2.
15. `coverage-table-scan / scan` — on `pull_request`, enforces the Coverage table on ≥3-bullet Linear issues. Requires `LINEAR_API_KEY`.
16. `check_instruction_drift.py` — scans `*.md` for stale check-count claims, retired-term leaks, and drifted safety-gate-scope enumerations. Runs inside `python / test`. Now also enforces CI gate count parity between the header, the enumerated list, and `all K gates` claims (Rule E, S5U-694).
17. `check_make_doc_parity.py` — fails CI when `make lint` in the `Makefile` drifts from the one-line summaries in CLAUDE.md and load-bearing templates (e.g. `docs/EXTRACTION_TICKET_TEMPLATE.md`). Fail-closed on missing `Makefile`/`CLAUDE.md`/template per `.claude/rules/guards.md` Rule G1. Runs inside `python / test` (S5U-690, PR #307).

CI also runs `pytest --tb=short` (full suite — includes slow tests, no timeout), unlike the pre-commit fast subset.

### What "passing" means

- **Local green** = safe to commit and push, but not sufficient for merge.
- **CI green** = all 18 gates pass — required for merge. "Definition of Done" means CI green.

## Safety-gate scope (canonical enumeration)

**Safety-gate scope escalation (MUST):** any PR touching safety-gate scope (hooks, pre-commit checks, review gates, CI checks, merge guards, branch-protection-adjacent scripts, `.claude/skills/**/SKILL.md` edits) MUST be shipped via `/coordinator`, not via `/ship` / `/next` / `/build-loop` run as a lone worker. Full workflow context in `AGENTS.md` § Development workflow step 6; mechanics in `.claude/rules/merge-discipline.md` § "Coordinator-ack mechanics".
