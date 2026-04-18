You are a software architect for the Aeon Trespass Expert project. Before implementation begins, produce a cross-subsystem plan for the current Linear issue.

## When to use this prompt

Use this plan whenever a change touches more than one subsystem, **or** when a single-subsystem change adds/modifies a safety gate (hook, review gate, CI check, merge guard):

| Subsystem | Path prefix |
|-----------|-------------|
| Pipeline | `apps/pipeline/` |
| Reader | `apps/web/` |
| Schemas | `packages/schemas/` |
| Config | `configs/` |
| Scripts | `scripts/` |
| DevOps | `.claude/`, `.github/` |

Examples: pipeline + reader, export + render, config + stage, schemas + pipeline.

## How to plan

1. Read the Linear issue description in full
2. Run `git diff main...HEAD` (if any exploratory changes exist)
3. Read the key files mentioned in the issue and their callers/consumers
4. Answer the questions below

## Required sections

### 1. Subsystems involved

List every subsystem this change will touch and the specific files/modules within each.

### 2. Cross-subsystem invariants

What contracts or assumptions connect these subsystems? Examples:
- Schema field X is read by both export and render — both must filter by edition
- Config key Y drives stage behavior — reader must handle its absence
- Function Z is called by three stages — changing its signature breaks all callers

### 3. Blast radius

For each subsystem being changed, what could break in the *other* subsystems?

```
Change in A → could break B because ...
Change in A → could break C because ...
```

### 4. Adversarial scenarios (safety/DevOps changes only)

A "safety/DevOps change" here means anything that adds or modifies a safety mechanism:

- Pre-commit hooks (`.claude/hooks/*.sh`, anything wired via `settings.json`)
- Review gates (`.claude/prompts/review.md`, `.claude/prompts/plan.md` itself, `.claude/rules/*.md` files that gate behavior)
- CI checks (`.github/workflows/*.yml`, composite actions under `.github/actions/**`)
- Merge guards (branch protection, pre-PR hooks, scripts invoked by any of the above under `scripts/check_*.{py,sh}`)
- `package.json` scripts invoked by any of the above (e.g., `test:e2e`)

Edits to this prompt (`plan.md`) and to `review.md` themselves count — they are review gates. Editing check severity or trigger wording in those files is a safety-gate change even when the diff looks small.

#### 4a. Tool surface citation (MANDATORY)

Before enumerating scenarios, **paste the relevant upstream tool surface inline**. The goal is to prove the plan was grounded in the tool's actual interface, not the author's memory of it:

- If the gate guards a CLI tool's flags: paste the output of `<tool> --help` (or the relevant excerpt from upstream docs) showing every flag alias, short/long form, and equivalent env var. Do not paraphrase — paste literal text.
- If the gate guards a config file: paste the schema / allowed-keys section from upstream docs or the repo's own schema file.
- If the gate guards a hook / workflow / prompt: paste the trigger block from the surrounding framework (e.g., the `when to use` table, the hook-registration entry in `settings.json`).
- If the tool surface is too large to paste in full, paste the section you audited and note what you excluded and why.

The plan is incomplete without this paste. "I know Playwright takes `--update-snapshots`" is exactly the failure mode S5U-608 caught — the author didn't know about `-u` because they didn't read the help text.

#### 4b. Equivalence classes (MANDATORY)

For each threat class, enumerate the **semantically-equivalent ways** to trigger the same condition and argue whether the gate covers each:

- Short vs long flags (`-u` vs `--update-snapshots`)
- Env-var equivalents (`PW_UPDATE_SNAPSHOTS=1`, `CI=false`)
- Wrapper scripts (`pnpm <script>` shortcuts, `npx <bin>`, direct `node_modules/.bin/<bin>` invocation)
- Sibling flags with equivalent effect (`--ignore-snapshots` disables the check instead of rewriting baselines)
- Passthrough arguments (`pnpm test -- --foo`, workflow `run:` passthrough, composite-action inputs)
- Allow-markers / opt-outs the guard itself honors

Each item concludes with **"covered"** (and how) or **"out of scope"** (and why — e.g., "requires write access to branch-protection, handled by coverage scope below").

#### 4c. Coverage scope (MANDATORY)

Name every location the threat surface can appear in this repo. For each, state whether the gate covers it:

- `package.json` scripts (which files — `apps/web/package.json`, `apps/pipeline/pyproject.toml` commands, etc.)
- Workflow `run:` lines (which workflow files, including sibling workflows that could invoke the same tool)
- Composite actions (`.github/actions/**`)
- Local hooks (`.claude/hooks/*.sh`)
- Branch-protection coverage (is this gate in the required-checks list on `main`?)
- Documentation / onboarding (CLAUDE.md, skill prompts) that could instruct future contributors to bypass the gate

Any location not covered must be explicitly excluded with rationale (e.g., "branch-protection edit is out-of-band; the plan names this as a known residual risk and the reviewer contract probes for it").

#### 4d. Three-scenario enumeration

For each gating condition, document at least three scenarios:

1. **Happy-path** — the gate allows a legitimate action (should pass)
2. **Failure input** — the gate blocks the condition it is designed to catch (should block)
3. **Adversarial edge** — an unexpected sequence defeats the gate (e.g., timing attack, granularity mismatch, stale data)

Common adversarial patterns to consider:
- **Timing attack** — unexpected order or delays (e.g., CI dispatch latency, race between push and status check)
- **Granularity mismatch** — file vs function, commit vs branch, run vs SHA
- **Stale data** — cached/previous results satisfying the check (e.g., old CI run for wrong commit)

Each scenario must conclude with: **"gate holds"** or **"gate defeated — fix needed."**

#### 4e. Worked example: S5U-599 → S5U-608 retro

This is the teaching case. The original `tmp/plan-s5u-599.md` enumerated "what if `--update-snapshots` is injected into the CI command" and declared the grep guard sufficient. Second-pass review (S5U-608) found four bypasses the plan missed. Here is what a tool-surface-first plan would have enumerated:

**4a Tool surface (retrospective paste):**

```
$ pnpm exec playwright test --help | grep -E -- '-(u|-update|-ignore)'
  -u, --update-snapshots [mode]    Update snapshots with actual results ...
      --ignore-snapshots           Ignore screenshot and snapshot expectations
```

Had the original plan pasted this, `-u` would have been visible in the audited surface. `--ignore-snapshots` would have been visible as a sibling flag that defeats the check via a different mechanism.

**4b Equivalence classes (retrospective):**

| Vector | Covered by original grep? | Should have been enumerated? |
|--------|---------------------------|------------------------------|
| `--update-snapshots` | Yes (grep matched) | Yes |
| `-u` (short flag) | **No** — grep only matched long form | Yes |
| `--ignore-snapshots` | **No** — different flag, same effect | Yes |
| `pnpm test -- -u` (workflow passthrough) | **No** — guard only read `package.json` | Yes |
| New sibling workflow invoking Playwright | **No** — guard only scanned one workflow | Yes |

**4c Coverage scope (retrospective):** the original plan scoped the guard to a single `package.json` script. The actual surface was: every `package.json` script across the repo, every `run:` line in every workflow under `.github/workflows/`, composite actions, and branch-protection's required-checks list. Only when S5U-608 added the `visual-gate-scope / scan` workflow did coverage align with the real surface, and even then S5U-611 found residual bypasses (allow-marker, bare `pnpm <script>` shortcut, branch-protection coverage) that hadn't been enumerated.

The lesson the new contract enforces: **the plan passes when the plan matches the tool's surface, not when the code matches the plan.**

Skip this entire section for non-safety changes (features, extraction, rendering, etc.).

### 5. Test strategy

For each risk identified in blast radius, what test would catch the breakage?
- Name the test file and describe the assertion
- If no test exists yet, mark it as **[NEW TEST NEEDED]**

### 6. Acceptance test planning (extraction work)

If this change involves extraction (stages, models, or fixtures under `apps/pipeline/`):

- **Pages under test:** List the specific page IDs named in the Linear issue or PR description (e.g., p0036, p0054). These are the pages where the fix must be verified.
- **Fixture/artifact source:** For each page, confirm a fixture or artifact exists that can be loaded in a test. If not, mark as **[FIXTURE NEEDED]**.
- **Assertions:** For each page, describe the concrete assertion that proves the claimed behavior (e.g., "p0054 contains a table block with 3 rows", "p0036 icon_label is 'Sword' not empty").
- **Synthetic vs real-page split:** Synthetic tests validate the algorithm in isolation; real-page tests validate the fix on the pages that motivated the issue. Both are required for extraction work — plan for both.

Skip this section for non-extraction changes (web, config, DevOps, etc.).

### 7. Implementation order

Sequence the changes to minimize risk:
1. Which subsystem should be changed first?
2. Where should you add/update tests before changing production code?
3. What can be validated at each step before moving to the next?

## Output format

Write the completed plan as a markdown document. Save it to `tmp/plan-s5u-<NUMBER>.md` (create `tmp/` if needed).

After completing the plan, pause and confirm the approach with the user before starting implementation. If running autonomously, review the plan yourself for gaps, then proceed.
