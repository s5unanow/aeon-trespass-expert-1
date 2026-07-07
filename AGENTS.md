# AGENTS.md — Compatibility Shim

**Canonical repo instructions live in [`CLAUDE.md`](CLAUDE.md).**

All agents should read and follow `CLAUDE.md` for:

- Project overview and repo layout
- Commands and quality gates
- Development workflow (Linear integration, branching, CI, merge policy)
- Conventions and safety rules (`NEVER` list)
- Session management (compacting, handoff)

If `AGENTS.md` and `CLAUDE.md` ever differ, **`CLAUDE.md` wins**.

## SDLC Factory Guides

Machine-readable mirror of `CLAUDE.md`/`.claude/rules/**` for tooling that reads `.ai-run/guides/` directly. `CLAUDE.md` remains authoritative; these guides are generated references, not a competing source of truth.

<!-- ai-run-init:guide-imports start -->
| Category | Guide Path | Purpose |
|---|---|---|
| Project context | `.ai-run/guides/project.md` | Ticket/MR adapters, source control target |
| Architecture | `.ai-run/guides/architecture/architecture.md` | IR-first pipeline + static reader system design |
| Testing (pipeline) | `.ai-run/guides/testing/pipeline-testing.md` | pytest commands, markers, cache-invalidation test rule |
| Testing (web) | `.ai-run/guides/testing/web-testing.md` | Vitest/Playwright commands, visual-regression gate |
| Development (pipeline) | `.ai-run/guides/development/pipeline-development.md` | Logging, error handling, atomic writes, cache invalidation |
| Development (web) | `.ai-run/guides/development/web-development.md` | Component/routing conventions |
| Standards (code quality) | `.ai-run/guides/standards/code-quality.md` | Lint/format/type-check commands and limits |
| Standards (git workflow) | `.ai-run/guides/standards/git-workflow.md` | Branch/commit/merge conventions |
| Security | `.ai-run/guides/security/security-practices.md` | CI guard discipline, hook/admin-merge disclosure |
| Integration | `.ai-run/guides/integration/llm-providers.md` | Translation LLM provider switching |
| Workflows | `.ai-run/guides/workflows/pipeline-workflow.md` | Extraction fixture/golden-refresh governance |
| Quality gates | `.ai-run/guides/quality-gates.md` | Full local + CI gate list |
<!-- ai-run-init:guide-imports end -->
