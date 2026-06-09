---
name: coordinator
description: Orchestrate multi-issue runs by spawning worker + reviewer subagents per issue. Use when user says "run coordinator", "ship N issues with review", "batch with independent review", or wants a worker/reviewer separation beyond `/build-loop`.
---

# Coordinator flow

Orchestrate a batch of Linear issues through ship + independent review + bug triage. You (the coordinator) never write code — you spawn subagents, verify their work, and manage the queue.

## When to use this vs `/build-loop`

- **`/build-loop`**: the user pair-programs with you; you ship issues directly, checkpoint between them.
- **coordinator**: the user wants autonomy with a reviewer-in-the-loop. Workers ship; separate reviewers scrutinize against the Linear description and file bugs in Linear when they find gaps. Useful for stress-testing recent work or running through a large queue while building a bug log.

## Before starting — ask

1. **How many issues** to ship (default: 5)
2. **Linear filter** (default: Backlog, unassigned, project ATE1, priority order Urgent → High → Normal)
3. **Worker model** (default: Opus as a *floor* — never silently downgrade a worker below the Opus tier; a stronger tier is fine, a weaker one is not)
4. **Reviewer model** (default: the strongest available model tier for **safety-gate scope** — adversarial review is one of the costliest failure surfaces and the cheapest to upgrade; Opus tier otherwise. A cheaper tier such as Sonnet is acceptable **only** as a first pass on simple, non-safety-gate work, and **only** when followed by a strongest-tier second pass — see step 5)
5. **On review-found bug**: (a) stop the run, (b) mark Urgent in Linear and continue — **default (b)**
6. **Strongest-tier second-pass review** after a cheaper first pass? (default: no, unless the first pass ran on a sub-Opus tier or the user explicitly wants two-pass)

Skip any question the user has already answered.

> **Capability-tier model policy (not hardcoded generations).** Model generations change faster than this skill doc, so express the policy in tiers, not names: the **coordinator itself** and **safety-gate reviewers** run on the *strongest available model tier* (as of 2026-06-09 that is Fable); **workers** default to the **Opus tier as a floor** (a stronger tier is fine; never silently downgrade below it). Concretely: orchestration/judgment failures and missed adversarial review findings are the costliest and the cheapest to upgrade — there is one coordinator and a handful of reviewers versus a fleet of workers, so spending the top tier there is the best marginal use of capability. Cross-vendor Codex review is unchanged.

## The loop — sequential, one issue at a time

For each issue in the queue:

### 1. Spawn worker subagent
- `subagent_type: "general-purpose"`, `model: <worker_model>`
- **Handshake sequence (S5U-670 ack supersedes the S5U-647 file marker):** the coordinator-ack commit status is posted on a SHA that already exists — i.e. **after** the worker has pushed. The full sequence is:
  **spawn → worker branches/commits/pushes → worker reports its pushed HEAD SHA → coordinator posts ack on that SHA → PR creation.** A status cannot be stamped on a SHA that does not yet exist, so there is no "post the ack before spawning" step.
- **Posting the ack** (run once the worker has reported its pushed HEAD):
  ```bash
  HEAD_SHA=<worker's reported pushed HEAD>   # verify it matches origin first (see below)
  gh api -X POST "repos/s5unanow/aeon-trespass-expert-1/statuses/$HEAD_SHA" \
    -f state=success \
    -f context=coordinator-ack \
    -f "description=S5U-<NUMBER> coordinator-ack"
  ```
  The pre-PR hook (`pre-pr-check.sh`) queries `gh api .../commits/<sha>/statuses`, filters for `context=coordinator-ack AND state=success`, and requires `creator.login` to match `.claude/coordinator-signers.txt`. GitHub stamps `creator.login` from the authenticated token — a worker cannot forge a status under your identity without access to your `gh auth` session. Posting the status here is the coordinator's explicit commitment to run the step-3 post-ship reviewer against the merged diff.
- **The prior file-marker mechanism (`tmp/.coordinator-ack-s5u-<N>`) is removed.** Do not `touch` local markers — they are no longer consulted by the hook (S5U-670 clean break). The only valid coordinator-ack evidence is a GH commit status from a signer in `.claude/coordinator-signers.txt`.
- **Post-ack continuation is harness-probing — do not hardcode SendMessage.** The harness moves: spawned agents return a `(use SendMessage to continue)` footer and the Agent-tool docs describe SendMessage continuation, but in some harness builds SendMessage is unavailable (ToolSearch finds nothing for it), so a worker paused before `gh pr create` cannot be resumed. Probe at runtime and pick the branch that exists:
  - **SendMessage available** → resume the paused worker and let it run `gh pr create`, watch CI, merge, sync, and flip Linear → Done itself. (If the resume worker pushes a new commit, see Failure handling — HEAD moves and the ack must be re-posted on the new SHA.)
  - **SendMessage unavailable** → the coordinator takes over inline (the paused worker cannot be resumed):
    1. Verify the remote HEAD equals the worker's reported SHA: `git fetch origin <branch> && git rev-parse origin/<branch>` — abort if they differ (the ack must pin the SHA that will be reviewed and merged).
    2. Confirm `gh api user --jq .login` is in `.claude/coordinator-signers.txt`.
    3. Post the `coordinator-ack` status on that SHA (command above).
    4. Run `gh pr create` yourself — the worker shares the filesystem, so its `tmp/review-s5u-<NUMBER>.md` + plan are already on disk and satisfy the pre-PR hook's artifact contract.
    5. `gh pr checks <N> --watch` → on green, `gh pr merge <N> --squash --delete-branch` → `git checkout main && git pull` → flip Linear → Done.
- **Non-safety-gate carve-out:** for issues that are NOT safety-gate scope, the pre-PR hook does not demand a coordinator-ack, so let the worker run end-to-end itself (its own `gh pr create` + CI watch + squash-merge + Linear → Done). The coordinator does not post an ack and does not run the PR for these; it only verifies (step 2) and reviews (step 3) after the worker reports the merge.
- Brief the worker with: Linear issue ID, working directory, full CLAUDE.md workflow obligations (plan if cross-system or safety-gate, branch, implement, local gates, mandatory sub-agent review per `.claude/prompts/review.md`, PR, CI, main-SHA verification, merge, sync, Linear → Done). For **safety-gate** issues, additionally instruct the worker to **stop after pushing and report its pushed HEAD SHA** — it must not attempt `gh pr create` (the hook will refuse it until the coordinator posts the ack).
- Ask for a report ≤300 words: PR URL (or pushed HEAD SHA + "stopped before PR" for safety-gate), merge SHA, CI pass summary, Linear confirmation, deviations, and — on failure — exact stop point + resume instructions

### 2. Verify inline (coordinator, no subagent)
- `git log --oneline -3 main` — confirm merge commit landed
- `gh pr view <N> --json state,mergeCommit,statusCheckRollup` — confirm MERGED + all required checks SUCCESS
- `mcp__plugin_linear_linear__get_issue` — confirm Linear status=Done

If any check fails, fix or abort — do not proceed to review as if shipped.

### 3. Spawn reviewer subagent
- `subagent_type: "general-purpose"`, `model: <reviewer_model>`
- **Preserve fresh eyes — pass only evidence, not worker narrative.** Include: merge SHA, PR URL, Linear issue ID, and the explicit reminder that the worker is NOT them. Do **NOT** pass the worker's report, rationale, commit messages, or their deviations list — these anchor the reviewer on the worker's framing and defeat the point of independent review. The reviewer must form its own read of the diff.
- Instruct:
  1. Fetch full Linear issue (description, success criteria, must-not-break, out-of-scope)
  2. `git show <sha>` — full diff; read changed files in full, not just hunks
  3. Probe each success criterion: is the behavior *actually* implemented, or just a file placeholder?
  4. Check NEVER-rule violations (handwritten TS, raw `print`, non-atomic writes, bare `except Exception`)
  5. Run targeted tests if cheap
  6. **Red-before evidence probe (S5U-615)** — if the diff adds any `def test_` (pytest) or `it(` / `test(` (vitest) function, grep commits + PR body for `red[- ]before` (case-insensitive). If absent, or if present as a bare phrase with no SHA / failure excerpt / explicit "N/A" carve-out, file it per the severity rules in `.claude/prompts/review.md` check #5. This probe must appear in `Probes run:`.
  7. Emit a **structured severity-tagged verdict** (see output contract below)
- On BUG: file each distinct gap as a Linear issue via `mcp__plugin_linear_linear__save_issue`:
  - `team="S5una"`, `project="ATE1"`, `priority=1` (Urgent), `state=Backlog`
  - Title: `S5U-XXX follow-up: <defect>`
  - Body: **Gap**, **Evidence** (file:line), **Repro**, **Fix sketch**, **Link** (PR+SHA), and for second-pass: **Why first-pass missed**
  - Labels: `["Bug"]` plus any topical match

### Reviewer output contract

Reviewer returns the following fields explicitly so the coordinator can make a deterministic BLOCK / PROCEED decision without re-parsing prose:

- **Verdict**: one of `PASS` | `BUG`
- **Critical** (blocks the ship): list of `{title, evidence, linear_id_if_filed}` — success-criterion gaps, NEVER-rule violations, safety-gate bypasses, false-green tests
- **Warning** (ship OK, fix soon): list of same shape — correctness concerns that don't invalidate the claimed behavior
- **Suggestion** (nits, not filed): inline list — style, ergonomics, deferred scope
- **Probes run**: bullet list of what was actually verified — **≥3 bullets, matching CLAUDE.md step 6** (trust but verify — this exposes reviewer laziness). For safety-gate PRs the block must also answer the S5U-659 mandatory adversarial question and record at least one novel variant per `.claude/prompts/review.md` check #16.
- **Bug IDs filed**: flat list for the coordinator's final report

Coordinator rule: if any `Critical` item exists, the issue is logged as BUG regardless of whether it was filed as a new Linear issue (some criticals may be declined as "pre-existing, out of scope"). `Warning`-only → PASS with warnings noted in final report.

### 4. Apply bug policy
- Default (b): bugs are Urgent in Linear, run continues to next issue
- (a) variant: stop run, report to user, let them decide

### 5. Optional strongest-tier second-pass review
If enabled, after a cheaper-tier first-pass PASS/BUG, spawn a **strongest-tier** reviewer (the top available model tier — see the capability-tier policy above) with the same brief plus:
- List of already-filed bugs (don't re-file)
- Explicit probe list appropriate to the change type (safety-gate = adversarial bypass probes — and for a corpus-backed detector per `apps/pipeline/tests/safety_gate_corpus/*.toml`, confirm any reviewer-found syntactic bypass was added to that corpus as a `block` case (or a corpus follow-up issue was opened), never patched in as a one-off regex per S5U-789; schema = contract direction; correctness-critical = end-to-end flow trace)
- Title bugs `S5U-XXX follow-up (second review): <defect>`

A stronger-model second pass consistently finds issues the first pass misses, especially on safety gates and complex correctness paths — which is why safety-gate reviewers should run on the strongest tier in the first place.

## Safety-gate / corpus CI gotchas

Two CI gates have bitten coordinator runs and are easy to miss mid-run. Brief workers on them so they aren't rediscovered:

- **`coverage-table-scan`** counts every list bullet in the Linear issue's **"Fix" + "Success criteria" sections only** (nested sub-bullets count; "Problem" / "Must not break" / "Out of scope" bullets do **not**). If the combined count is ≥3, the PR body must carry a `## Coverage` table with **one row per bullet, verbatim** — no merged or collapsed rows. See `.claude/prompts/linear-conventions.md` § "Coverage table format".
- **`check_detector_corpus_coverage`** binds `.claude/prompts/review.md` to the `instruction_drift` corpus: any edit to `review.md` requires a paired corpus touch, or the sanctioned `# coverage-waiver: S5U-XXX <reason>` comment when the review.md edit is genuinely orthogonal to the corpus-bound probe. A review.md edit with neither a corpus diff nor a waiver comment fails CI.

## Failure handling

- **Worker stalls mid-task**: check branch/PR/Linear state yourself. If PR exists and CI passed, merge inline. If branch exists but no PR, spawn a small resume agent briefed with the exact state. If nothing pushed, spawn a fresh worker with the Linear issue state.
- **Resume worker pushes a new commit (safety-gate branch)**: any resume agent that pushes a new commit moves the branch HEAD, so the earlier `coordinator-ack` status — pinned to the old SHA — no longer covers the SHA that will be merged. **Re-post the ack on the new HEAD** (re-run the `gh api -X POST .../statuses/<new-sha>` command) before that worker retries `gh pr create`, and before merging. The post-merge audit (`.github/workflows/post-merge-coordinator-ack.yml`) checks the merged HEAD, so a stale ack on a superseded SHA will fail the audit even if the PR merged. The same applies to an amend: an amend after ack changes the HEAD SHA and requires a fresh ack — this is intended behavior.
- **Worker reports unrecoverable failure**: report to user with the worker's own stop-point description. Do not silently retry.
- **Reviewer-filed bug blocks CI on main**: stop the queue, tell the user — running on a red main is wrong.
- **Queue exhausted before N reached**: report what shipped, what's still in Backlog, stop.

## Final report

At end of run:
- Table: issue | PR | merge SHA | review verdict (PASS / BUG → list IDs)
- Total merged, total bugs filed
- Observations: patterns across workers/reviewers (e.g., "3 of 5 cross-system issues produced bugs on first review; the strongest-tier second pass caught 7 more gaps on top")
- Any process deviations noticed (worker skipped mandatory step, rule doc stale, etc.)

## Rules

- Sequential, never parallel — branches and Linear state race otherwise
- Never skip inline verification — a worker report is intent, not evidence
- Never delegate synthesis: you decide what's shipped, what's blocked, what to tell the user
- Keep task list (`TaskCreate`/`TaskUpdate`) accurate so progress is visible
- Match review depth to change class: safety-gate > correctness > feature > polish

## Coordinator is the authoritative gate for safety-critical work (S5U-628)

Under the current harness, sub-agents spawned by `/build-loop`, `/next`, and `/ship` do NOT have the `Agent` tool available, so their pre-PR review is a lone-worker inline self-review (CLAUDE.md step 6 Path B). That fallback is acceptable for feature/polish changes but **not** for safety-gate scope per CLAUDE.md (which includes `.claude/skills/` SKILL.md edits as an operational path).

Per CLAUDE.md step 6, safety-gate PRs MUST be shipped via `/coordinator`. The coordinator's step-3 reviewer subagent — spawned *after* merge, with only evidence (merge SHA, PR URL, Linear ID) and an explicit "you are not the worker" reminder — is the authoritative fresh-eyes gate for this class of change. Run that reviewer on the strongest available tier (per the capability-tier policy above), and treat any safety-gate issue that arrives here as a high-priority candidate for the strongest-tier second-pass review option.

**Coordinator-ack signal (S5U-647 → S5U-670):** per the step-1 handshake, the coordinator posts a `coordinator-ack` commit status to GitHub on the worker's pushed HEAD SHA — after the push, before PR creation (whether the resumed worker or the coordinator itself runs `gh pr create`). This is the machine-enforced signal that the coordinator flow is in play — `pre-pr-check.sh` refuses `gh pr create` on safety-gate-scoped branches unless the GH API returns a `coordinator-ack` status with `state=success` and `creator.login` ∈ `.claude/coordinator-signers.txt`, closing the lone-worker bypass that the former user-override clause in `/ship` enabled. The status is the coordinator's *commitment* to run the step-3 reviewer; failing to run the reviewer after the worker merges is a coordinator-level safety-gate violation. The prior file-marker mechanism (`tmp/.coordinator-ack-s5u-<N>`) was worker-forgeable (S5U-670 retrospective: 7 of 7 PRs in the 2026-04-20 coordinator run had worker-written markers) and has been removed — only GH-API-authenticated commit statuses count.
