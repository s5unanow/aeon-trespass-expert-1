# AGENTS.md

**Two authorities, two jobs.** [`CLAUDE.md`](CLAUDE.md) remains the canonical
source for this repo's Linear-tracked development workflow, quality-gate
enumeration, and safety rules (`NEVER` list) — read it for project overview,
commands, branching/CI/merge policy, and session management. This file is the
**SDLC Factory guide index**: a generated, per-module map into `.ai-run/guides/`
for factory skills and any agent that wants a quick category → guide lookup
instead of re-deriving conventions from source. Where a rule in the tables
below and `CLAUDE.md` ever conflict on workflow, gates, or safety policy,
**`CLAUDE.md` wins** — these tables are a derived index, not a replacement.

## Guide Imports

<!-- ai-run-init:guide-imports start -->
| Category | Guide Path | Purpose |
|---|---|---|
| Project Context | `.ai-run/guides/project.md` | Ticket adapter (Linear), source control (GitHub), MR adapter (`gh`) |
| Quality Gates | `.ai-run/guides/quality-gates.md` | Exact lint/type/test commands, ordered fastest-to-slowest |
| Git Workflow | `.ai-run/guides/standards/git-workflow.md` | Branch naming, commit format, merge strategy |
| Pipeline — Architecture | `apps/pipeline/.ai-run/guides/architecture/architecture.md` | Layered stage/runner architecture + import-linter contract |
| Pipeline — Development | `apps/pipeline/.ai-run/guides/development/development-practices.md` | Logging, atomic writes, stage-output cache-invalidation rule |
| Pipeline — Testing | `apps/pipeline/.ai-run/guides/testing/testing-patterns.md` | pytest structure, markers, fixture/golden-refresh governance |
| Pipeline — Standards | `apps/pipeline/.ai-run/guides/standards/code-quality.md` | ruff/mypy/import-linter/file-length rules |
| Web — Architecture | `apps/web/.ai-run/guides/architecture/architecture.md` | React/Vite/Router structure, generated-types boundary |
| Web — Testing | `apps/web/.ai-run/guides/testing/testing-patterns.md` | vitest + Playwright visual-regression gate |
| Web — Standards | `apps/web/.ai-run/guides/standards/code-quality.md` | oxlint/tsc/prettier rules |
| Schemas — Architecture | `packages/schemas/.ai-run/guides/architecture/architecture.md` | Pydantic → JSON Schema → TS codegen contract |
<!-- ai-run-init:guide-imports end -->

## Task Classifier

<!-- ai-run-init:task-classifier start -->
| Category | User Intent | Example Requests | P0 Guide | P1 Guide |
|---|---|---|---|---|
| Pipeline logic | Modify extraction/translation/QA/render stages, runner, services | "add a QA rule", "fix the translation fallback" | `apps/pipeline/.ai-run/guides/architecture/architecture.md` | `apps/pipeline/.ai-run/guides/development/development-practices.md` |
| Pipeline testing | Write/run pipeline tests | "add a pytest for the QA stage" | `apps/pipeline/.ai-run/guides/testing/testing-patterns.md` | `apps/pipeline/.ai-run/guides/standards/code-quality.md` |
| Web reader | Modify components/routes/styles | "fix the page renderer", "add a route" | `apps/web/.ai-run/guides/architecture/architecture.md` | `apps/web/.ai-run/guides/standards/code-quality.md` |
| Web testing / visual regression | Add vitest/Playwright tests, refresh baselines | "add a component test", "update the visual snapshot" | `apps/web/.ai-run/guides/testing/testing-patterns.md` | - |
| Schema / codegen | Modify Pydantic models, regenerate JSON Schema + TS types | "add a field to the page IR model" | `packages/schemas/.ai-run/guides/architecture/architecture.md` | `.ai-run/guides/quality-gates.md` |
| Quality gates / CI | Run or diagnose lint/type/test gates | "why did CI fail", "run the quality gates" | `.ai-run/guides/quality-gates.md` | - |
| Git / PR workflow | Commit, push, open a PR | "commit this", "create a PR" | `.ai-run/guides/standards/git-workflow.md` | `.ai-run/guides/project.md` |
<!-- ai-run-init:task-classifier end -->

## Critical Rules

<!-- ai-run-init:critical-rules start -->
| Rule | Trigger | Action |
|---|---|---|
| Check Guides First | ANY task | Match request → category → load the P0 guide before searching the codebase broadly |
| Repo Workflow & Safety Gates | ANY task in this repo | Read `CLAUDE.md` first — authoritative for this repo's Linear-tracked workflow, safety-gate escalation, and `NEVER` list; the guides above are a derived index, not a substitute |
| Testing | "write tests" / "run tests" | Only then; load the relevant module's `testing/testing-patterns.md` |
| Git Operations | "commit" / "push" / "PR" | Only then; load `.ai-run/guides/standards/git-workflow.md` |
| Shell | ANY shell command | bash/Linux-compatible syntax only |
<!-- ai-run-init:critical-rules end -->

## Commands

<!-- ai-run-init:commands start -->
| Need | Source Guide | Source Evidence | Notes |
|---|---|---|---|
| Lint / format | `.ai-run/guides/quality-gates.md` | `Makefile`, `pyproject.toml`, `apps/web/package.json` | Load guide before running |
| Type check | `.ai-run/guides/quality-gates.md` | `Makefile` (`mypy`, `tsc --noEmit`) | Load guide before running |
| Tests | `.ai-run/guides/quality-gates.md` | `Makefile`, `pyproject.toml` | Fast subset locally, full suite in CI |
| Codegen | `packages/schemas/.ai-run/guides/architecture/architecture.md` | `Makefile`, `scripts/generate_jsonschema.py`, `scripts/generate_ts_types.mjs` | Run after any Pydantic model change |
| Git / review workflow | `.ai-run/guides/standards/git-workflow.md` | git history, `CLAUDE.md` | Load guide before git operations |
<!-- ai-run-init:commands end -->
