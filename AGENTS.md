# AGENTS.md — Aeon Trespass Expert

Primary AI entrypoint. Load the relevant `.ai-run/guides/` file (and any path-scoped
`.claude/rules/*.md`) **before** changing code. Exact standards and commands live in the
guides, not here.

**What this is:** IR-first document compiler + static web reader for Aeon Trespass rulebook
translation (EN→RU). Monorepo: `apps/pipeline` (Python 3.12 compiler), `apps/web` (React 19
/ Vite reader), `packages/schemas` (Pydantic→JSONSchema→TS), `packages/fixtures`.

## Guide Imports

<!-- ai-run-init:guide-imports start -->
| Category | Guide Path | Purpose |
|---|---|---|
| Project context | .ai-run/guides/project.md | Identity, Linear ticket adapter, GitHub PR adapter |
| Architecture | .ai-run/guides/architecture/architecture.md | Staged IR pipeline, layer contract, key abstractions |
| Development | .ai-run/guides/development/development-practices.md | Python/TS conventions, atomic IO, cache invalidation |
| Testing | .ai-run/guides/testing/testing-patterns.md | pytest/vitest/Playwright, red-before, visual regression |
| Code quality | .ai-run/guides/standards/code-quality.md | ruff/mypy/oxlint/import-linter, generated schemas |
| Git workflow | .ai-run/guides/standards/git-workflow.md | Branch/commit/merge conventions (S5U-, squash) |
| Quality gates | .ai-run/guides/quality-gates.md | make lint/typecheck/test/check/codegen commands |
| Integration | .ai-run/guides/integration/external-integrations.md | LLM adapters, PDF/layout, provider switching |

Note: `AGENTS.md` has no native import directive — this is a plain reference table.
Detailed path-scoped conventions remain authoritative in `.claude/rules/*.md` (auto-loaded
on file match) and architecture decisions in `docs/adrs/`.
<!-- ai-run-init:guide-imports end -->

## Task Classifier

<!-- ai-run-init:task-classifier start -->
| Category | User Intent | Example Requests | P0 Guide | P1 Guide |
|---|---|---|---|---|
| Architecture | Understand/extend the pipeline | "add a stage", "how does render work" | .ai-run/guides/architecture/architecture.md | .claude/rules/pipeline.md |
| Development | Write pipeline/web code | "implement X in the pipeline" | .ai-run/guides/development/development-practices.md | .claude/rules/pipeline.md, web.md |
| Testing | Add or run tests | "write tests", "why is CI red" | .ai-run/guides/testing/testing-patterns.md | .claude/rules/hooks.md |
| Standards | Lint/format/type/schema | "fix lint", "regenerate schemas" | .ai-run/guides/standards/code-quality.md | .claude/rules/schemas.md |
| Git / review | Branch, commit, PR, merge | "commit", "open a PR", "merge it" | .ai-run/guides/standards/git-workflow.md | .claude/rules/merge-discipline.md |
| Integration | LLM / extraction backends | "swap translation provider" | .ai-run/guides/integration/external-integrations.md | docs/specs/translation-providers.md |
| Extraction | Extraction tickets | "improve block extraction" | .claude/rules/extraction.md | docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md |
<!-- ai-run-init:task-classifier end -->

## Critical Rules

<!-- ai-run-init:critical-rules start -->
| Rule | Trigger | Action |
|---|---|---|
| Check Guides First | ANY task | Match request → category → load the P0 guide before searching broadly |
| Path rules | Editing a scoped path | Read the matching `.claude/rules/*.md` (pipeline, web, schemas, extraction, hooks, guards, visual-verify, merge-discipline) |
| Testing | "write tests" / "run tests" | Load `.ai-run/guides/testing/testing-patterns.md`; record red-before evidence for new tests |
| Git Operations | "commit" / "push" / "PR" | Load `.ai-run/guides/standards/git-workflow.md`; use `S5U-` prefix; never `--no-verify` without disclosure |
| Schemas | Changing a Pydantic model | Run `make codegen`; never hand-edit generated `jsonschema/` or `ts/` |
| Shell | ANY shell command | bash/Linux-compatible syntax |
<!-- ai-run-init:critical-rules end -->

## Commands

<!-- ai-run-init:commands start -->
| Need | Source Guide | Source Evidence | Notes |
|---|---|---|---|
| Bootstrap / install | .ai-run/guides/quality-gates.md | Makefile:6 | `make bootstrap` |
| Lint / format | .ai-run/guides/quality-gates.md | Makefile:10,22 | Load guide before running |
| Type check | .ai-run/guides/quality-gates.md | Makefile:27 | mypy + tsc |
| Tests | .ai-run/guides/quality-gates.md | Makefile:31 | pytest + vitest |
| Full local gate | .ai-run/guides/quality-gates.md | Makefile:35 | `make check` = lint+typecheck+test |
| Codegen | .ai-run/guides/standards/code-quality.md | Makefile:57 | After Pydantic model changes |
| Git / PR workflow | .ai-run/guides/standards/git-workflow.md | git history | Load before git operations |
<!-- ai-run-init:commands end -->

## Development Workflow (MANDATORY)

All work is tracked in **Linear** (project **ATE1**, team **S5U**). Every change follows:

1. **Pick up an issue** — user-specified, or highest-priority unassigned Backlog issue; mark In Progress.
2. **Branch** — `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-short-description` (hook-enforced).
3. **Plan** — cross-subsystem or safety-gate changes run `.claude/prompts/plan.md` → `tmp/plan-s5u-<N>.md`.
4. **Work** — commit with `S5U-XXX:` prefix; the 9 local gates run via pre-commit hook.
5. **Definition of done** — see the checklist below; local `make check` green **and** CI green.
6. **Independent fresh-eyes review** (MANDATORY before PR) — Path A (spawn review agent with
   `.claude/prompts/review.md`) if the Agent tool is available, else Path B inline self-review.
   Safety-gate-scoped PRs must ship via `/coordinator` (`.claude/rules/merge-discipline.md`).
7. **Create PR** — `git push -u origin HEAD`; `gh pr create`; link the Linear issue.
8. **Wait for CI** — `gh pr checks <n> --watch`; never merge red.
9. **Merge & sync** — `gh pr merge <n> --squash --delete-branch`; sync main; set Linear Done.

Rollback is `git revert <merge-sha>` (never rewrite history on main). Emergency admin bypass
requires a `## Admin-merge disclosure` (`.claude/rules/merge-discipline.md`).

## Quality Gates

Two tiers, both must pass. **CI green is the definition of done** — local green is necessary
but not sufficient. Details and exact commands: `.ai-run/guides/quality-gates.md`.

- **Local pre-commit** (`.claude/hooks/pre-commit-check.sh`, <60s): secret guard + ruff check
  + ruff format + mypy strict + import-linter + file-length + oxlint + tsc + fast pytest subset.
- **CI** (GitHub Actions): all local gates plus codegen-freshness, fixture-manifest,
  extraction-scope, golden-refresh, visual-regression (`maxDiffPixelRatio: 0.005`),
  visual-gate-scope, coverage-table-scan, instruction-drift, make/doc-parity.

## NEVER

- Never use `git reset --hard` or `git push --force` on main.
- Never commit `.env`, credentials, API keys, or secret files.
- Never write manual TypeScript types (generate from Pydantic via `make codegen`).
- Never add bare `except Exception` without structured logging.
- Never skip the fresh-eyes review before creating a PR.
- Never commit directly to main (use feature branches).
- Never merge with failing CI.
- Never skip pre-commit hooks without a `## Hook bypass disclosure` (`.claude/rules/hooks.md`).
- Never merge with admin-bypass without a `## Admin-merge disclosure` (`.claude/rules/merge-discipline.md`).

## Conventions & Context Management

- Commit prefix `S5U-XXX:`; config format is TOML.
- Path-scoped conventions in `.claude/rules/` (auto-loaded); Linear conventions in
  `.claude/prompts/linear-conventions.md`.
- Before batch/multi-step work, check `scripts/` for a purpose-built tool.
- On long-session end, write `HANDOFF.md` at repo root (gitignored). `/compact` between task
  phases; `/clear` when switching issues.

> Historical note: `AGENTS.md` was previously a shim pointing at `CLAUDE.md`. Authority is now
> inverted — `AGENTS.md` is canonical and `CLAUDE.md` imports it via `@AGENTS.md`.
