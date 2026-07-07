# AGENTS.md

Primary AI entrypoint for `aeon-trespass-expert` — an IR-first document compiler (Python pipeline) + static React reader monorepo. Load the relevant `.ai-run/guides/` file before changing code. Deep, path-scoped conventions live in `.claude/rules/*.md` (auto-loaded on file match) and are the authoritative source for safety-gate detail.

> Monorepo note: `AGENTS.md` has no native import directive — the tables below use plain guide paths. `CLAUDE.md` is a Claude Code shim that imports this file via `@AGENTS.md`.

## Guide Imports

<!-- ai-run-init:guide-imports start -->
| Category | Guide Path | Purpose |
|---|---|---|
| Architecture (system) | .ai-run/guides/architecture/architecture.md | Map of the IR-first pipeline → web system, ADRs, cross-cutting boundaries |
| Architecture (pipeline) | .ai-run/guides/architecture/pipeline.md | Python compiler internals: stages, executor, cache, artifact store |
| Architecture (web) | .ai-run/guides/architecture/web.md | React 19 static reader: routing, generated-types contract, components |
| Schemas & codegen | .ai-run/guides/architecture/schemas-codegen.md | One-way Pydantic → JSON Schema → TS contract |
| Testing | .ai-run/guides/testing/testing-patterns.md | pytest (markers, red-before, cache-hit) + vitest + Playwright visual regression |
| Development | .ai-run/guides/development/development-practices.md | Cross-cutting Python/TS conventions, error handling, atomic writes |
| Quality gates | .ai-run/guides/quality-gates.md | Local + CI gate commands, pass/fail, auto-fix |
| Git workflow | .ai-run/guides/standards/git-workflow.md | Branch/commit/merge conventions (Linear-tracked) |
| Project context | .ai-run/guides/project.md | Identity, Linear ticket adapter, GitHub PR adapter |
<!-- ai-run-init:guide-imports end -->

## Task Classifier

<!-- ai-run-init:task-classifier start -->
| Category | User Intent | Example Requests | P0 Guide | P1 Guide |
|---|---|---|---|---|
| Pipeline change | Modify extraction/translation/QA stages | "add a QA rule", "fix the render stage" | .ai-run/guides/architecture/pipeline.md | .ai-run/guides/testing/testing-patterns.md |
| Web change | Modify the React reader | "fix page rendering", "add a block type" | .ai-run/guides/architecture/web.md | .ai-run/guides/testing/testing-patterns.md |
| Schema change | Change a shared data shape | "add a field to the IR", "new payload type" | .ai-run/guides/architecture/schemas-codegen.md | .ai-run/guides/architecture/architecture.md |
| Testing | Write or run tests | "write tests", "run tests" | .ai-run/guides/testing/testing-patterns.md | .ai-run/guides/quality-gates.md |
| Quality / CI | Run gates, fix a failing check | "run lint", "why is CI red" | .ai-run/guides/quality-gates.md | - |
| Git / review | Commit, push, open a PR | "commit", "create a PR", "merge it" | .ai-run/guides/standards/git-workflow.md | .ai-run/guides/project.md |
| Onboarding / design | Understand the system, draft an ADR | "how does this work", "cross-system refactor" | .ai-run/guides/architecture/architecture.md | - |
<!-- ai-run-init:task-classifier end -->

## Critical Rules

<!-- ai-run-init:critical-rules start -->
| Rule | Trigger | Action |
|---|---|---|
| Check Guides First | ANY task | Match request → category → load the P0 guide before searching broadly |
| Testing | "write tests" / "run tests" | Only write or run tests when requested or needed for verification; follow `.ai-run/guides/testing/testing-patterns.md` (red-before discipline is mandatory) |
| Git Operations | "commit" / "push" / "PR" | Only then; load `.ai-run/guides/standards/git-workflow.md` — every commit is `S5U-<NNNN>:` prefixed |
| Shell | ANY shell command | Use bash/Linux-compatible syntax |
| Path-scoped rules | Editing pipeline/web/schemas/hooks/CI | Honor the auto-loaded `.claude/rules/*.md` for that path — authoritative for safety gates |
| Safety-gate scope | Editing hooks, CI checks, merge guards, review gates | Ship via `/coordinator` (coordinator-ack required); read `.claude/rules/merge-discipline.md` before changing |
| Never bypass silently | Bypassing a hook or admin-merging | Disclose per `.claude/rules/hooks.md` / `.claude/rules/merge-discipline.md` — concealment is the stronger violation |
<!-- ai-run-init:critical-rules end -->

## Commands

<!-- ai-run-init:commands start -->
| Need | Source Guide | Source Evidence | Notes |
|---|---|---|---|
| Bootstrap deps | .ai-run/guides/quality-gates.md | Makefile (`make bootstrap`) | uv sync + pnpm install |
| Lint / format | .ai-run/guides/quality-gates.md | Makefile (`make lint` / `make format`) | Load guide before running |
| Type check | .ai-run/guides/quality-gates.md | Makefile (`make typecheck`) | mypy + tsc |
| Tests | .ai-run/guides/quality-gates.md | Makefile (`make test`) | pytest + vitest |
| Full local gate | .ai-run/guides/quality-gates.md | Makefile (`make check`) | Canonical "definition of done" aggregate |
| Codegen / freshness | .ai-run/guides/architecture/schemas-codegen.md | Makefile (`make codegen` / `make check-codegen`) | After any Pydantic model change |
| Git / review workflow | .ai-run/guides/standards/git-workflow.md | git history, `.claude/hooks/` | Load guide before git operations |
<!-- ai-run-init:commands end -->

## Repository Rules (authoritative — preserved, not duplicated)

Deep operating discipline is not restated here; load the authoritative file:

| Area | Authoritative source |
|---|---|
| Full dev workflow (pick issue → PR → merge → sync) | `CLAUDE.md` history / `.ai-run/guides/standards/git-workflow.md` + `.claude/prompts/linear-conventions.md` |
| NEVER list (no force-push/reset on main, no secrets, no manual TS types, no bare except, no silent hook/admin bypass) | `.claude/rules/{merge-discipline,hooks}.md` |
| Pipeline conventions (logging, atomic writes, stage-cache invalidation) | `.claude/rules/pipeline.md` |
| Web / schemas conventions | `.claude/rules/web.md`, `.claude/rules/schemas.md` |
| CI guard discipline (fail-closed, content-derived) | `.claude/rules/guards.md` |
| Visual regression gate | `.claude/rules/visual-verify.md` |
| Extraction playbook | `docs/EXTRACTION_IMPLEMENTATION_PLAYBOOK.md`, `.claude/rules/extraction.md` |
| Architecture (deep) + ADRs | `docs/PROJECT_ARCHITECTURE.md`, `docs/adrs/` |
