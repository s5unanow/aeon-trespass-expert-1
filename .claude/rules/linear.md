---
description: Linear issue creation conventions — applies when creating or updating issues via MCP
globs: ""
---

When creating a Linear issue (`mcp__linear__save_issue`), always set:

## Labels (required — at least one area + one type)

**Area** (where the work lives):
- `Pipeline` — Python backend: stages, LLM, models, schemas
- `Reader` — React frontend: components, styles, routing
- `DevOps` — CI, hooks, skills, tooling, CLAUDE.md, AGENTS.md
- `Config` — TOML configuration externalization
- `QA` — Quality assurance rules, validation logic
- `Testing` — Test coverage and infrastructure

**Type** (what kind of change):
- `Bug` — defect in existing behavior
- `Regression` — behavior that worked before a recent change broke it
- `Feature` — new capability
- `Improvement` — enhancement to existing capability
- `Refactor` — architecture cleanup, tech debt reduction

## Milestone

Assign to the matching milestone if the work clearly fits one:
- **Config-Driven Structure** — externalizing hardcoded constants to TOML
- **Patch & Frontend** — patch system, document discovery, reader features

If no milestone fits, leave it unset — do not force-fit.

## Parent issue

If the work belongs to an existing epic, set `parentId`:
- S5U-191 — Epic 8: Evidence fusion and hard-page routing (extraction pipeline)
- S5U-192 — Epic 9: Translation robustness and blocking release QA
- S5U-144 — Epic 3: Config-driven structure recovery
- S5U-146 — Epic 5: Patch application + dynamic document discovery

## Must not break (required for Bug, Regression, Improvement, Refactor)

When creating issues of these types, include a **"Must not break"** section listing invariants the implementation must preserve. Each entry should name the invariant and briefly explain why it matters.

Examples:
- "Edition filtering — EN export must never include RU content"
- "Existing `glossary_mentions` on pages that already have them"
- "`mypy --strict` passing on all changed files"

If there are genuinely no invariants at risk, write "None identified" — do not omit the section.

Skip this section only for `Feature` issues (net-new capabilities with no existing behavior to protect).

## Dependencies

Set `blockedBy` when the issue genuinely cannot start until another is Done.
Do not add soft/nice-to-have ordering as blocking dependencies.

## Fix issues

When creating fix issues for post-ship audit findings:
- Always include `Bug` label (or `Regression` if it broke prior behavior)
- Reference the original issue in the description (e.g., "post-ship audit of S5U-XXX")
- Set `blockedBy` if the fix depends on another fix landing first
