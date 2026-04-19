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

## Must refuse (required for Bug, safety-gate, cross-system-review; recommended for Feature/Improvement/Refactor touching security-sensitive paths)

Enumerate the **adversarial inputs, invalid states, and out-of-contract callers the change must reject at runtime**. This section exists because happy-path descriptions keep shipping bugs that an explicit refusal list would have caught: S5U-594 → S5U-607 (path traversal via unsanitized `page_id`), S5U-595 → S5U-610 (edition cross-contamination on a QA URL the pipeline never filtered by).

**"Must refuse" ≠ "Out of scope".** "Out of scope" is what this change **won't implement**. "Must refuse" is what the implemented code **must actively reject at runtime**. Never merge the two. If the rejection is a non-goal ("we're not validating page_ids yet"), call it out in **both** sections — once as scope, once as a documented refusal gap.

**When it fires:**
- **Required** for issues labeled `Bug`, `safety-gate`, or `cross-system-review`.
- **Strongly recommended** for `Feature` / `Improvement` / `Refactor` when the change touches **filesystem paths, user-supplied identifiers that flow into I/O, serialization, external process invocation, network boundaries, or authentication/authorization**.
- **Optional** otherwise.

**How to draft this section** — list concrete refusals, not abstract categories:

1. **Input shape** — which fields come from untrusted callers? Name each, and for each list at least one invalid value the code must reject (out-of-range, wrong type, null, empty, oversized).
2. **Filesystem and I/O** — if the code writes to paths derived from input: enumerate path-traversal vectors (`..`, absolute paths, symlinks, null bytes, encoded separators), forbidden characters, length limits, reserved names.
3. **Cross-tenant / cross-edition isolation** — if the code filters by edition / language / document / user: enumerate what leaks if the filter is dropped or bypassed.
4. **Concurrency** — if the code writes shared state: enumerate the race conditions it must refuse (lost updates, double-writes, partial state).
5. **Contract violations** — inputs that are well-formed but out of contract for this caller (wrong IR version, mismatched schema, stale cache key).

**Format:** bullet list. Each bullet: `"<input/condition> → <refusal behavior>"`.

**Worked example (retrospective, drafted as if S5U-594 had carried this section):**

> - `page_id` containing `..` / absolute paths / null bytes → reject with 400, do not touch filesystem
> - `page_id` not matching `^[a-z0-9_-]{1,64}$` → reject with 400
> - `issue_type` outside the enum `{rendering, translation, layout, other}` → reject with 400
> - `timestamp` older than 24 h or in the future → reject with 400
> - Request body > 10 KiB → reject with 413 before deserialization
> - Any filesystem write path that resolves outside `artifacts/feedback/<edition>/<page_id>/` after `realpath` → refuse the write, log structured error

If none of these apply (e.g., pure refactor with no input surface), write **"None — this change has no untrusted input surface."** Do not omit the section.

A pre-ship reviewer can cite any specific "Must refuse" bullet to justify a BLOCK verdict when the diff fails to implement it.

## Semantically-equivalent threats (required for safety-gate, cross-system-review, Bug; optional for Feature/Improvement/Refactor)

For any **enforcement, validator, gate, or check** this change adds or modifies, enumerate the **semantically-equivalent ways the condition can be triggered or bypassed**. This section exists because S5U-599 enforced `--update-snapshots` but not the equivalent `-u`, `--ignore-snapshots`, workflow-level passthrough, or sibling-workflow invocation — shipping a gate with four bypasses (S5U-608).

**When it fires:**
- **Required** for issues labeled `safety-gate`, `cross-system-review`, or `Bug` where the fix adds/tightens a check.
- **Optional but recommended** for `Feature` / `Improvement` / `Refactor` that add any kind of validator, guard, or filter.
- Skip for pure refactors or docs changes with no enforcement logic.

**How to draft this section** — enumerate the tool surface, not your mental model of it:

1. **Short vs long flags** — if the gate reads a CLI flag, list every short/long/alias form the tool accepts (`<tool> --help` output is ground truth, not memory).
2. **Environment variables** — does the tool honor env vars with the same effect as the flag? (`PW_UPDATE_SNAPSHOTS`, `CI`, `NO_COLOR`, etc.)
3. **Wrapper scripts / passthrough** — `pnpm <script>` shortcuts, `npx <bin>`, direct `node_modules/.bin/<bin>`, workflow `run:` passthrough (`pnpm test -- -u`), composite-action inputs.
4. **Sibling flags with equivalent effect** — different flag, same outcome (`--ignore-snapshots` disables the check instead of rewriting baselines).
5. **Schema aliases / config keys** — if validating a config field, list every alias (`snake_case`, `camelCase`, deprecated spellings) the schema accepts.
6. **Coverage locations** — every file, workflow, package.json script, composite action, and documentation page the threat can appear in.

**Format:** table or bullet list. For each vector state **covered** (and how) or **out of scope** (and why).

**Worked example (retrospective, drafted as if S5U-599 had carried this section):**

> | Vector                                           | Covered? |
> |--------------------------------------------------|----------|
> | `--update-snapshots` in `package.json`           | Yes — grep rule in `visual-regression.yml` |
> | `-u` short flag                                  | Yes — grep rule matches both forms |
> | `--ignore-snapshots` (sibling flag, same effect) | Yes — grep rule includes this alias |
> | `pnpm test -- -u` (workflow passthrough)         | Yes — scan covers all workflow `run:` lines |
> | New sibling workflow invoking Playwright         | Yes — `visual-gate-scope / scan` walks every `.github/workflows/*.yml` |
> | `PLAYWRIGHT_UPDATE_SNAPSHOTS=1` env var          | Out of scope — Playwright does not honor this env var (verified via `--help`); note as "re-audit if upstream adds env-var support" |
> | Branch-protection required-check list            | Out of scope for this ticket — manual audit, tracked in follow-up |

This enumeration feeds directly into `.claude/prompts/plan.md` §4b (equivalence classes) for the downstream planner. Populating it well at the Linear level saves the planner from re-deriving it badly.

**"N/A" is allowed only with justification.** `"Semantically-equivalent threats: N/A — this change adds no enforcement logic (pure render refactor)"` is acceptable. `"Semantically-equivalent threats: N/A"` with no justification is a reviewer BLOCK cue on a required-label issue.

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

**When the rule fires:** count every list marker (`-`, `*`, numbered) at any indent level in the "Fix" and "Success criteria" sections of the Linear issue — **nested sub-bullets count**. A parent with 5 children is 6 bullets, not 1. Bullets in "Problem," "Must not break," or "Out of scope" do **not** count. If the combined count is `< 3`, the table is optional (reviewer judgment). If the issue uses prose instead of bullets, the table is optional — reviewer falls back to qualitative judgment.

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
- Do **not** merge rows or collapse bullets. **One row per bullet, verbatim** — including nested sub-bullets. If a parent bullet has N nested sub-bullets, the table must have N+1 rows (parent + each child), not a single row citing the parent. This is the S5U-622 correction: earlier prompt versions left nested-counting semantics ambiguous, which let single-row parent entries silently hide dropped sub-bullets.

**What the independent reviewer probes** (`.claude/prompts/review.md` check #19):
- Counts the Linear issue's Fix + Success criteria bullets at every indent level. If `≥ 3`, the Coverage table is mandatory.
- Walks each row and confirms the cited file/commit actually implements the bullet (not just a plausible-looking path).
- **Samples at least one nested sub-bullet by name** when the issue has nested structure, and verifies it has its own row and independent mapping — a parent-only spot-check is not enough.
- For deferred rows, calls `mcp__plugin_linear_linear__get_issue` on the cited follow-up ID and confirms it exists and is not Canceled.
- Blocks (CRITICAL) on any unaddressed bullet, any missing table on a ≥3-bullet issue, any nested sub-bullet collapsed under a parent row without its own row, or any fake/Canceled follow-up reference.

**Worked example (honest framing, S5U-621)** — earlier prompt versions cited S5U-594 as a 5-bullet case with `role="dialog"`, `aria-modal="true"`, focus trap, focus restoration, and initial focus. That example was fabricated: S5U-594's actual Linear description has 3 numbered Fix items (Reader UI / Submission path / Intake) with nested sub-bullets about the floating button, form fields, and intake path. ARIA attributes, focus trap, focus restoration, and initial focus appear nowhere as verbatim bullets — they were implicit a11y requirements the worker failed to derive. **The Coverage-table gate catches verbatim-bullet drops, not implicit-requirement gaps.** S5U-594's focus-trap regression (S5U-609) is an implicit-a11y drift failure mode, which is a separate concern this gate does not address.

A real worked example that the gate **does** catch, once the S5U-622 nested-bullet rule is applied: S5U-595's "Reader route" Fix bullet has 4 verbatim nested sub-bullets (including the `block_id` highlight that silently dropped in the original ship as S5U-601). A compliant Coverage table for S5U-595 would have one row for the `Reader route` parent plus four rows for each nested sub-bullet; collapsing the four children into the parent row is now a CRITICAL per check #19 ("Nested sub-bullet collapsed under parent row — verbatim one-row-per-bullet rule violated").
