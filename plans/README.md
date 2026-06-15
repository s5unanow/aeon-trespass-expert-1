# Advisor plans — improve pass

- **Generated:** 2026-06-10
- **Planned-at commit:** `fc98b82` (main)
- **Produced by:** one-time read-only advisor pass (4 parallel audit agents: pipeline, web/schemas, CI/guards, tests/deps/docs → ~38 findings → vetted against source → top 5 planned)
- **Hard constraint honored:** no source files modified; only `plans/` created.

## How to execute these plans

Every plan is self-contained and follows the repo's mandatory workflow (CLAUDE.md is canonical):
Linear issue (project ATE1, team S5U) → branch `s5unanow/s5u-XXX-short-description` → commits prefixed `S5U-XXX:` → local gates → independent fresh-eyes review → PR → CI green → squash-merge. **Do not push or open PRs unless the user instructs.** Plans 002 and 004 touch safety-gate scope and MUST ship via `/coordinator` (coordinator-ack commit status required by `pre-pr-check.sh`).

## Recommended execution order

| # | Plan | Priority | Effort | Risk | Safety-gate scope | Status |
|---|------|----------|--------|------|-------------------|--------|
| 1 | [001-executor-cache-integrity.md](001-executor-cache-integrity.md) | P0 (silent-wrong-output) | S | LOW | No | TODO |
| 2 | [002-precommit-hook-fail-open.md](002-precommit-hook-fail-open.md) | P0 (gate integrity) | S–M | MED | **Yes — /coordinator** | TODO |
| 3 | [003-export-bundle-atomicity.md](003-export-bundle-atomicity.md) | P1 (data integrity) | S | LOW | No (visual-verify applies) | TODO |
| 4 | [004-ci-caching-and-concurrency.md](004-ci-caching-and-concurrency.md) | P1 (CI cost/latency) | S | LOW | **Yes — /coordinator** | TODO |
| 5 | [005-reader-navigation-data-caching.md](005-reader-navigation-data-caching.md) | P1 (user-facing perf + UX bugs) | M | LOW | No (visual-verify applies) | TODO |

Dependency notes:
- Plans are independent of each other; any order works.
- 001 is first because it removes a silent-stale-cache class that undermines trust in every pipeline rerun — including the held RU-edition rerun (S5U-997), which depends on cache behavior being correct.
- 002 and 004 both edit safety-gate scope; they can be batched into one coordinator session but must remain **separate PRs** (002 is hook correctness with adversarial scenarios; 004 is workflow efficiency).
- 004 changes workflow YAML only — run `make verify-branch-protection` after merge (required-check context names must not change).
- 005 will likely require visual-baseline awareness (it changes reader-page mount behavior); 003 touches `scripts/export_to_web.py`, which is on the visual-verify path list.

## Findings considered and not planned (vetted; candidates for follow-up Linear issues)

High value, deferred for size/design reasons:
- **Count-only stage summaries make downstream cache keys lossy** (`stages/translation/stage.py:61-66`, `stages/structure/stage.py:46-52`, `stages/extract_layout/stage.py:18-24` — upstream content can change while `pages_built`/counts stay equal → stale downstream cache hits; `RenderResult` already does it right with per-page `page_refs`). M effort / MED risk; needs a design pass + version bumps across 4 stages. Natural follow-up to plan 001.
- **`--from <stage>` starts with empty `upstream_refs`** (`cli/commands/run.py:98-104`) — aliased cache-key space across different upstream content. Same family as above; fix together.
- **TranslationStage has no per-page failure resume** (`stages/translation/stage.py:230-244`) — one failed page discards the whole run's LLM spend on retry. NOTE: HANDOFF.md claims "per-page translate is cached"; reconcile that claim (likely refers to stage-level cache on success, not mid-run failure) before filing.
- **Persisted `translation_meta.primary_error` is null even when the primary provider failed** (observed in the S5U-997 run: all 83 pages fell back to gemini, no recoverable agy error). Diagnose in `services/llm/` fallback path; high diagnostic value for the RU rerun.
- **mtime is the store's only "latest" signal intra-pipeline** (`store/artifact_store.py:129`, `store/edition_selection.py:106-119`) — L effort; export path was already hardened (S5U-869/890), pipeline-internal reads were not.
- **QA stage re-parses every historical artifact JSON per run** (`store/edition_selection.py:106-119` parses all candidates to read one field; renders loaded twice per page) — M effort perf fix, grows with store history.
- **Pre-commit hook latency ~2× its <60s target** (measured ~97s for the pytest subset alone; `slow` marker registered in `pyproject.toml:134` but used by **zero** tests, so the "fast subset" is the full suite). Fix = mark genuinely slow tests + consider `pytest-xdist`. Safety-gate scope.
- **Guard-script helper duplication** (`_verify_ref_exists`/`get_changed_files` copy-pasted across ~6 `scripts/check_*.py`, signatures already drifting) — extract `scripts/_git_baseline.py`. Safety-gate scope.
- **Docs-only PRs run the full Playwright + slow-pytest stack** (no path scoping in `ci.yml`) — MED-risk to implement safely with required checks; do after 004.
- **`make lint` omits `check_instruction_drift.py`** which CI runs with no CI-specific inputs (`python-tests.yml:49-50`) — local green ≠ CI green for `*.md` edits. Beware: `check_make_doc_parity.py` requires updating CLAUDE.md's `make lint` one-liner in the same PR.

Smaller quick wins (file as chore issues):
- Silent `except Exception: pass/continue` without logging at `stages/extract_native/pymupdf_extractor.py:94` and `services/pdf/image_extractor.py:104-106` — violates the repo's own NEVER rule.
- E2E console-error filter swallows all failed resource loads (`apps/web/tests/e2e/extraction-regression.spec.ts:21-23` — `text.includes('Failed to load resource')` discards every 404; filter on `msg.location().url` instead).
- `PRIMARY_TYPES` hand-map in `scripts/generate_ts_types.mjs:22-58` silently skips 5 existing schemas — derive from schema `title` or fail loudly on unmapped stems (G2-style content-derived fix).
- `pyyaml` imported by `scripts/check_branch_protection.py:19` and `scripts/_instruction_drift_rule_d.py:30` but undeclared (resolves transitively) — add `pyyaml>=6.0` to root dev group.
- `pydantic` used directly in 28 pipeline modules but undeclared in `apps/pipeline/pyproject.toml` — add it.
- Storybook scripts in `apps/web/package.json:17-18` but Storybook is not installed anywhere — delete scripts + doc mentions (or install).
- `apps/web/dist-node/` build outputs tracked in git (incl. `.tsbuildinfo`) — untrack + gitignore.
- `python / test` installs unpinned `npm install -g pnpm` (`python-tests.yml:65`) vs `version: 10` elsewhere — folded into plan 004.
- Stale unreferenced `reports/quality_audit.json` + `reports/improvement_plan.md` committed — remove or document.

Considered and rejected:
- 36.5 MB copyrighted rulebook PDF in git (`materials/ATO_CORE_Rulebook_v1.1.pdf`) — real, but remediation (LFS/history rewrite) is an owner-level decision for a private single-user repo; flagging, not planning.
- `typescript@^6.0.0` / `@types/node@^25` pins — MED confidence near knowledge cutoff; revisit only if CI breaks.
- `docs/PROJECT_ARCHITECTURE.md` §13 layout drift (≥7 divergences) + 27-line README — worth doing but pure docs; lower leverage than the five planned items.
- structlog/orjson/stdlib-logging style items — explicitly sanctioned as-is by `.claude/rules/AUDIT.md`.

## Status values

`TODO | IN PROGRESS | DONE | BLOCKED | REJECTED` — update the table above as plans execute.
