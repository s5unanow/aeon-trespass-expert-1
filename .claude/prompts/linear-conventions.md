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

**Execution mode** (modifier — combine with area + type labels):
- `cross-system-review` — Triggers mandatory Codex second review in `/ship` workflow

## When to apply `cross-system-review`

Apply this label when the issue's implementation will **cross subsystem boundaries** and the contract between subsystems is non-trivial. A second-model review (Codex) catches interface mismatches that a single reviewer misses.

**Apply when:**
- Change spans **pipeline + web** (e.g., new IR field that the reader must render)
- Change spans **schemas + pipeline** (e.g., Pydantic model change that affects stage contracts)
- Change spans **schemas + web** (e.g., generated TS type consumed by new component)
- Change affects **export + render** (e.g., export script changes that alter what the web app receives)
- Change modifies a **shared config** consumed by both pipeline and web
- Change adds a **new data flow path** between any two subsystems

**Do NOT apply when:**
- Change is isolated to one subsystem (only pipeline stages, only web components)
- Change is config/docs/DevOps only (no cross-boundary data flow)
- Change is a pure refactor within one subsystem boundary

**Examples:**
- "Add `glossary_mentions` field to IR and render tooltips in reader" → YES (schemas + pipeline + web)
- "Fix CSS spacing on sidebar component" → NO (web only)
- "Add new extraction stage for evidence blocks" → NO (pipeline only, unless it adds new IR types)
- "Externalize render config to TOML and consume in both pipeline and web" → YES (config + pipeline + web)

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

**How to draft this section** — before writing the issue, investigate:

1. **Current outputs** — run the affected code on representative pages/inputs and note what it produces today. These outputs are your invariants.
2. **Cross-stage / cross-edition contracts** — if the change touches a pipeline stage, check what downstream stages consume its output. If it touches filtering (edition, language, document), list every filter dimension that must be preserved.
3. **Existing tests** — run `uv run pytest -x -q --timeout=60 -m "not slow"` and name specific test functions that cover the area being changed. These tests must stay green.

Each invariant should follow the pattern: `"<what> — <why it matters>"`.

Examples:
- "Edition filtering — EN export must never include RU content"
- "Existing `glossary_mentions` on pages that already have them"
- "`mypy --strict` passing on all changed files"
- "`test_render_icon_inline_spacing` — verifies icon-to-text separator logic"

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

## Coverage table format (multi-bullet issues)

When the Linear issue you are shipping has **≥3 explicit bullets across its "Fix" + "Success criteria" sections**, the PR body must include a **Coverage table** that maps each bullet to the commit or file that addresses it. This is a CLAUDE.md Definition-of-Done requirement (step 5) motivated by S5U-616 after repeated dropped-bullet regressions (S5U-594 → S5U-609, S5U-595 → S5U-601, S5U-605).

**When the rule fires:** count bullets only in the "Fix" and "Success criteria" sections of the Linear issue. Bullets in "Problem," "Must not break," or "Out of scope" do **not** count. If the combined count is `< 3`, the table is optional (reviewer judgment). If the issue uses prose instead of bullets, the table is optional — reviewer falls back to qualitative judgment.

**Table format** — put this in the PR body under a `## Coverage` heading:

```markdown
## Coverage

| # | Bullet (verbatim from Linear)                                           | Addressed by                              |
|---|-------------------------------------------------------------------------|-------------------------------------------|
| F1 | (Fix bullet 1) Add field `X` to model                                  | `apps/pipeline/src/...model.py` (this PR) |
| F2 | (Fix bullet 2) Export `X` in artifact bundle                           | `scripts/export_to_web.py` (this PR)      |
| F3 | (Fix bullet 3) Render `X` as tooltip in reader                         | deferred to S5U-YYY (follow-up filed)     |
| S1 | (Success criterion 1) p0036 shows tooltip on hover                     | `apps/web/tests/e2e/tooltip.spec.ts`      |
| S2 | (Success criterion 2) EN export never includes RU content              | `tests/test_export_validation.py` (existing coverage preserved) |
```

- Prefix row IDs with `F` for Fix bullets and `S` for Success criteria (order matches the Linear issue).
- Quote or paraphrase each bullet tightly enough that the reviewer can match it to the Linear source.
- In the **Addressed by** column, cite one of:
  - A file path in the PR diff (`path/to/file.ext`) — the reviewer will skim the diff to confirm.
  - A commit SHA on this branch.
  - An existing file (for preserved invariants) with a brief note.
  - `deferred to S5U-YYY` with a real follow-up issue ID (the follow-up must exist in Linear and not be Canceled; reviewer will look it up).
- If a single file/commit addresses multiple bullets, list it on each row — duplication is fine.
- Do **not** merge rows or collapse bullets. One row per bullet, verbatim.

**What the independent reviewer probes** (`.claude/prompts/review.md` check #19):
- Counts the Linear issue's Fix + Success criteria bullets. If `≥ 3`, the Coverage table is mandatory.
- Walks each row and confirms the cited file/commit actually implements the bullet (not just a plausible-looking path).
- For deferred rows, calls `mcp__plugin_linear_linear__get_issue` on the cited follow-up ID and confirms it exists and is not Canceled.
- Blocks (CRITICAL) on any unaddressed bullet, any missing table on a ≥3-bullet issue, or any fake/Canceled follow-up reference.

**Worked example** — S5U-594 (reader feedback button) had 5 bullets: `role="dialog"`, `aria-modal="true"`, focus trap, focus restoration, initial focus. A compliant Coverage table would have listed all 5 rows. The actual PR #242 would have had rows only for #1–#2, making rows #3–#5 missing entries that the reviewer (per check #19) would have flagged as CRITICAL — catching the gap before merge rather than after (it shipped as S5U-609).
