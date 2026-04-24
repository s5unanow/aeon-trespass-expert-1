---
description: Merge-time discipline rules — admin-bypass disclosure, branch-protection context handling, and stale-context carve-outs
globs: .github/workflows/**,.github/actions/**,scripts/check_*.py,scripts/check_*.sh,scripts/verify_*.py,CLAUDE.md,.claude/prompts/review.md,.claude/prompts/plan.md
---

# Merge discipline

This rule codifies the requirements around admin-bypass of branch-protection and
the disclosure contract that makes concealment detectable. The short-form rule
lives in the CLAUDE.md NEVER list ("Never merge with admin-bypass without
disclosure"); this file holds the full vector enumeration, reviewer-probe
semantics, stale-context carve-out history, and retrospectives.

## Admin-merge disclosure (S5U-671, extended S5U-675)

### The rule

Any merge that bypasses one or more of GitHub's branch-protection gates
(required status checks, `strict: true` outdated-branch, CODEOWNERS /
required-review, conversation resolution, signed commits, linear history) MUST
be documented in the PR body under a level-2 `## Admin-merge disclosure`
heading. The section must name:

1. The specific protected surface that was bypassed (required check, strict
   branch, CODEOWNERS, conversation-resolution, etc.).
2. Why admin-merge was appropriate (stale-context class vs infrastructure
   outage vs branch-freshness vs other).
3. What the worker did to verify the bypassed surface independently.

Admin-merge vectors the rule covers:

- `gh pr merge --admin`
- REST `PUT /repos/{owner}/{repo}/pulls/<N>/merge` with admin privileges (no
  `--admin` token in REST; admin privilege is implicit when the caller is
  admin).
- GitHub UI "Merge without waiting for requirements" button.
- GitHub audit-log events `pull_request_review_bypass` and
  `pull_request_review_merge`.

### Concealment is the stronger violation

An undisclosed admin-bypass is **CRITICAL** regardless of whether the
bypassed surface was truly benign. A disclosed admin-bypass (heading + (a)
(b) (c) populated) is **WARNING** — audit-trail finding.

### Scope

The rule applies to PRs opened **after** S5U-671 landed. Historical
admin-merges (PRs #282–#288 from 2026-04-20) predate the rule and are not
retroactively audited.

### Reviewer probe (check #25 in `.claude/prompts/review.md`)

The probe runs in two passes:

1. **Required-status-check pass (S5U-671 surface)** — fetches the PR HEAD SHA
   (`gh pr view <N> --json headRefOid`), queries check-runs on the PR HEAD
   (`gh api repos/.../commits/<head_sha>/check-runs`), and — if any required
   check was not `success` at merge time — greps the PR body for the
   disclosure heading. Absent heading on a bypassed check is CRITICAL.
2. **Token-grep pass (S5U-675, parallel to check #22)** — runs **regardless of
   check-run state**, greps merge-commit message + PR body + PR comments for
   admin-merge vocabulary (`--admin`, `gh api PUT /pulls/.../merge`,
   `pull_request_review_bypass`, `pull_request_review_merge`,
   `Merge without waiting for requirements`, `admin-merge`, `admin-bypass`,
   `bypass branch protection`). Catches bypasses of **non-status-check**
   surfaces that pass (1) cannot see.

Severity table (abbreviated; authoritative grid is in review.md check #25):

- Canonical-CLI match in merge-commit message or PR body **without** the
  disclosure heading — **CRITICAL** (concealment).
- Canonical-CLI match in PR comments only, no disclosure heading —
  **WARNING** (conversational self-report is partial disclosure).
- Prose paraphrase (`admin-bypass`, `bypassed branch protection`) with no
  canonical token and no disclosure — **WARNING** (higher FPR).
- All required checks SUCCESS on PR HEAD, no tokens anywhere — silent pass.

Pass (1) queries the PR HEAD SHA, **not** the merge commit SHA. Pre-S5U-674
the probe queried the merge commit SHA, which false-positived on every
`pull_request`-only required check (e.g., `coverage-table-scan / scan` — a
`push`-only workflow never emits a check-run against the merge commit's
`push: main` event). S5U-674 fixes this by querying the PR HEAD SHA, which
accumulates every check-run that actually gated the merge.

### Stale-context carve-out (S5U-664, narrowed by S5U-674)

A required-context name whose check-run is **absent** from the PR HEAD
response (never reported at all, as opposed to reported-and-failed) may be a
stale-context mismatch — i.e., the workflow posts under a different name
than branch protection requires (e.g., the workflow's `jobs.<id>.name`
doesn't match the branch-protection context string). If a sibling check-run
with a different-but-related name exists and has `conclusion=success`, this
is the S5U-664 pattern.

Worker disclosures citing S5U-664 are accepted only while S5U-664 is
unfixed. S5U-664 shipped Done 2026-04-20T16:46Z, so new disclosures citing
S5U-664 without evidence of a fresh name-mismatch occurrence grade WARNING —
the worker should have investigated the real cause of the context-name
mismatch rather than leaning on a closed tracking issue.

Post-S5U-674, this carve-out no longer absorbs the `pull_request`-only
artifact class (that was a probe bug, fixed by querying PR HEAD); the
carve-out now covers only genuine workflow-name-mismatch.

### Non-status-check surfaces the token-grep pass closes (S5U-675)

Before the token-grep pass, a worker could admin-merge any non-status-check
surface (CODEOWNERS, strict-branch, conversation-resolution, signed commits,
linear history) with **all required checks green** and leave zero detectable
signal even if they self-reported the bypass in a PR comment. S5U-675 closes
that class by running the token grep regardless of check-run state.

### Concrete precedent — PR #307 (S5U-690 / merge SHA `b8e281e`)

PR #307 merged with no coordinator-ack status on its HEAD and no required
status check configured to block it. The post-merge audit layer
(`.github/workflows/post-merge-coordinator-ack.yml`, S5U-693) was added after
this incident to catch the exact class — safety-gate-scoped merges that
bypass the local pre-PR hook by using GitHub web UI, `gh api -X POST
.../pulls`, or a sub-agent harness that does not inherit `.claude/settings.json`
hook wiring.

### Residuals (not probe-detectable)

The reviewer probe does NOT detect:

- An admin-merge with **zero side-channel trace** — worker used no admin-merge
  vocabulary in commit message, PR body, or PR comments, AND all required
  status checks were SUCCESS on PR HEAD. Worker-honesty-backed gap.
- A disclosure whose cited "independent verification" text is a fabrication —
  the reviewer can spot-check cited commands but cannot replay arbitrary
  prose.
- A merge that bypassed branch protection via `rulesets` overrides rather
  than the classic `required_status_checks` endpoint (this repo uses classic
  branch protection; rulesets are out of scope).
- Cross-line evasive paraphrases of admin-merge outside the token vocabulary
  (e.g., "force-pushed past the gate", "used my admin toggle").
- A worker who admin-merges and then rebases/force-pushes a sanitizing edit
  over the PR body/comments before the reviewer runs the probe.
- A new required context added to branch protection **after** the PR HEAD was
  last pushed but before merge — the PR HEAD SHA won't have a check-run for
  it; grading row is WARNING unless the absent context is known to have been
  failing on a prior PR-HEAD SHA.

The backstop is worker honesty, framed by "concealment is the stronger
violation than the bypass itself." The post-merge audit workflow
(S5U-693) is the complementary audit-trail layer — a red run on `main` is
itself a reviewer-cross-referenced finding.

## Coordinator-ack mechanics (S5U-670, S5U-693)

The short-form rule in CLAUDE.md §6 names the coordinator-ack commit status
and the post-merge workflow. This section is the rationale — why the design
is the way it is, and what came before.

### Why GitHub commit status, not file marker

Pre-S5U-670, `pre-pr-check.sh` looked for a `tmp/.coordinator-ack-<issue>`
file marker. The 2026-04-20 coordinator run observed **7 of 7** PRs with
worker-written markers — the marker was worker-forgeable (nothing prevented
a worker from `touch tmp/.coordinator-ack-s5u-XXX` before running `gh pr
create`). S5U-670 removed the file marker and replaced it with a GitHub API
commit status check.

GitHub stamps `creator.login` on every commit status from the authenticated
OAuth token. A worker cannot post a status under the coordinator's identity
without the coordinator's `gh auth` session. The allowlist
`.claude/coordinator-signers.txt` pins which `creator.login` values count as
"valid coordinator-ack".

### Why fail closed on degenerate inputs (S5U-666)

The coordinator-ack hook is a safety gate, so it follows `.claude/rules/guards.md`
Rule G1 (fail-closed defaults). Every degenerate input — base ref
unresolvable, GH API unreachable, allowlist file missing, malformed status
response — exits non-zero, not "no ack found → permissive."

### Why a post-merge audit workflow (S5U-693)

The pre-PR hook only intercepts **local** `gh pr create`. A PR opened via
GitHub web UI, `gh api -X POST .../pulls`, or a sub-agent harness that does
not inherit `.claude/settings.json` hook wiring **bypasses the hook entirely**.
PR #307 (merge SHA `b8e281e`) was merged without any coordinator-ack status
on its HEAD — the concrete precedent.

`.github/workflows/post-merge-coordinator-ack.yml` closes this gap: on every
`push` to `main`, it identifies commits whose diff matches the safety-gate
regex and fails the workflow unless a valid coordinator-ack is found on the
PR HEAD SHA (or the merge commit range).

The workflow is **not** a required-check context in branch protection — it
cannot block merge (required checks are PR-time gates, not post-merge
events). But a red run is a durable Actions-tab audit signal, and the
reviewer's check #16 "Merge-time coordinator-ack probe" cross-references it
as a second-pass detection.

Scope clauses:

- Applies to PRs opened after S5U-670 landed (historical PRs predate the
  hook and are not retroactively audited).
- Worker-honesty residual: a coordinator-authenticated `gh auth` session
  compromised or shared with a worker defeats the gate — detection is out of
  scope for the mechanical layer; the backstop is the CLAUDE.md NEVER-list
  framing of concealment as the stronger violation.
