# Git Workflow

## Branch pattern

```
s5unanow/s5u-<LINEAR_ID>-<short-description>
```

**Examples:**
- `s5unanow/s5u-1475-kf2-haiku`
- `s5unanow/s5u-1233-docs-only-prs-short-circuit-ci`

**Enforcement:** Hook blocks commits to `main` and rejects branches that don't match the pattern (enforced in `.claude/hooks/pre-commit-check.sh`).

## Commit format

```
S5U-<LINEAR_ID>: <description>
```

**Example:**
```
S5U-1475: draft SDLC Factory foundation guides (project, git-workflow, quality-gates)
```

**Rules:**
- Prefix is mandatory (`S5U-NNNN:`)
- Description is present tense, concise (under 72 chars preferred)
- One commit per logical change; squash before PR if needed

**Git log shows:**
```
1f377ca S5U-1233: docs-only PRs short-circuit the rendering CI jobs (in-job, fail-closed) (#445)
437a67b S5U-1232: extract scripts/_git_baseline.py — dedup verify_ref_exists / get_changed_files (#444)
```

## Workflow steps (canonical)

### 1. Start work

```bash
git checkout main
git pull
git checkout -b s5unanow/s5u-<ID>-description
```

### 2. Work on branch

Make changes, write tests (with red-before evidence for new tests).

```bash
git add <files>
git commit -m "S5U-<ID>: description"
```

Pre-commit hook runs 9 gates automatically. If any fail, fix and re-commit (don't amend — create a new commit).

### 3. Verify local gates

```bash
make check  # Runs lint + typecheck + test
```

Expected output: all 9 gates green.

### 4. Independent review

**If `Agent` tool is available (you):**
```bash
# Spawn reviewer agent
# (handled by `/coordinator` or `/ship` skill)
```

**If `Agent` not available (sub-agent context):**
```bash
# Self-review: walk `.claude/prompts/review.md` checks 1–25
# Write tmp/review-s5u-<N>.md
# Disclose in PR body: "Reviewed under Path B (Agent unavailable in sub-agent context)"
```

**Result:** `tmp/review-s5u-<N>.md` with structured verdict (Verdict, Critical, Warning, Probes, Bug IDs filed).

### 5. Push and create PR

```bash
git push -u origin HEAD
gh pr create --title "..." --body "..."
```

**PR body must include:**
- Linear issue link (e.g., "Closes S5U-1475")
- Test plan (what did you verify?)
- Coverage table (if ≥3 Linear bullets — see `.claude/prompts/linear-conventions.md` § "Coverage table format")
- Retry/edge-case notes (if any)

### 6. CI waits

```bash
gh pr checks <N> --watch
```

All 18 gates must pass (9 local + 9 CI). Branch protection blocks merge if any required check fails. Do not merge red.

### 7. Merge (squash)

```bash
# Pre-flight: verify main CI is green and SHA matches current main HEAD
gh api repos/s5unanow/aeon-trespass-expert-1/branches/main --jq '.commit.sha'

# Merge with squash (consolidates all branch commits into one)
gh pr merge <N> --squash --delete-branch
```

Squash-merge ensures `main` has one commit per feature/fix (PR number in commit body).

### 8. Sync and mark done

```bash
git checkout main
git pull

# Update Linear issue
mcp__linear__save_issue(id="S5U-<ID>", state="Done")
```

## Anti-patterns (NEVER)

| Anti-pattern | Why | Alternative |
|--------------|-----|-------------|
| `git reset --hard` or `git push --force` on main | Rewrites history; breaks reflog and audit trail | Use `git revert` (new commit) for unwinding |
| Direct commits to main | Branch names are untracked, tests may not run | Always use feature branch (`s5unanow/s5u-...`) |
| `git commit --no-verify` or `-n` flag | Bypasses pre-commit hook; gates fail silently | Let hook run; fix failures and re-commit. If bypassed, **disclose in PR** with `## Hook bypass disclosure` heading |
| `HUSKY=0`, `LEFTHOOK=0`, `SKIP=`, etc. | Silently disables hook runner | Use `git commit --no-verify` if truly needed, and **disclose** |
| Merge without CI green | Bypasses required checks; breaks main | Wait for CI or escalate to emergency admin-merge (rare; requires disclosure) |
| Multiple simultaneous PRs from same branch | Conflicting merges; unclear ownership | One branch → one PR → squash-merge → branch delete |
| Amending old commits and re-pushing | Rewrites branch history; loses reflog | Create a new commit instead; squash at PR time if needed |

**Concealment is the stronger violation.** An undisclosed hook bypass or admin-merge is CRITICAL (see `.claude/rules/hooks.md` § "Hook-bypass disclosure" and `.claude/rules/merge-discipline.md` § "Admin-merge disclosure").

## Test discipline (required for new tests)

Every PR adding a new `def test_` (pytest) or `it(` / `test(` (vitest) function must include red-before evidence:

```
Red-before confirmation: commit <sha> shows <test_name> failing with "<assertion excerpt>"
```

Or:

```
Red-before confirmation: ran locally at <sha>^ (fix reverted); output: "<short excerpt of failure>"
```

Or (N/A carve-out):

```
Red-before confirmation: N/A — no production code change in this PR (test documents existing invariant); reviewer asked to cross-check diff
```

See `.claude/rules/hooks.md` § "Three-input test discipline" for SHA-resolution tripwire and scope carve-outs.

## Troubleshooting

### Pre-commit hook fails

**Symptom:** `git commit` exits non-zero with error message.

**Cause:** One or more of the 9 local gates failed (lint, format, mypy, imports, file-length, oxlint, tsc, pytest, fixtures, codegen, instruction-drift, make-doc-parity).

**Fix:**
1. Read the error message carefully. It names the failing check.
2. Run that check in isolation: e.g., `uv run ruff check .` or `make format`.
3. Many checks auto-fix; run `make format` first.
4. For mypy/pytest errors: read the diff and fix the code.
5. Stage corrected files and re-commit (new commit, don't amend).

### "Base ref unresolvable" or shallow checkout

**Symptom:** CI guards fail with "Base ref ... is unresolvable — CI checkout likely shallow."

**Cause:** GitHub Actions cloned with `fetch-depth: 0` not set; PR comparison fails.

**Fix (if CI):** This is a workflow issue, not worker issue. Report to DevOps.

### Branch protection blocks merge

**Symptom:** "Branch protection rule failed" even though all checks pass locally.

**Cause:** Required check context registered in branch protection but not appearing in PR. Usually stale-context drift (workflow renamed but branch protection not updated).

**Audit:** `make verify-branch-protection` (runs post-workflow-change). If drift found, add new context via append-only endpoint (see `.claude/rules/visual-verify.md` § "Adding a new top-level quality gate — branch-protection append rule").

### Merge SHA doesn't match main HEAD

**Symptom:** `gh api repos/.../branches/main --jq '.commit.sha'` returns a different SHA after merge.

**Cause:** Another PR merged to main in the interim; your base is stale.

**Fix:** Retry up to 3 times with 10s delay before assuming a real stale-SHA issue (see CLAUDE.md step 9).

### "Reviewed under Path B" and sub-agent

**Symptom:** You are a sub-agent under `/coordinator`, `/ship`, `/build-loop`, or `/next` and don't have `Agent` tool available.

**Expected path:** Path B (inline self-review). Walk `.claude/prompts/review.md` checks 1–25; write `tmp/review-s5u-<N>.md`; disclose Path B in both artifact and PR body.

**Do NOT claim Path B at top level** if `Agent` is available — that's a safety-gate violation (see CLAUDE.md § 6, "Bypass clauses").

## Coordinator-ack for safety gates

**When it matters:** Any PR touching hooks, pre-commit checks, review gates, CI checks, branch protection, or `.claude/skills/**/SKILL.md`.

**Pre-PR check (local):** `.claude/hooks/pre-pr-check.sh` refuses `gh pr create` unless the branch HEAD has a valid `coordinator-ack` commit status from a signer in `.claude/coordinator-signers.txt`.

**How to get it:** Run `/coordinator` skill on the safety-gate branch. Coordinator spawns a fresh-eyes reviewer and signs the branch with `coordinator-ack` status when approved.

**Post-merge audit:** `.github/workflows/post-merge-coordinator-ack.yml` re-checks every `push` to main for safety-gate-scoped diffs; fails if no valid coordinator-ack found.

See `.claude/rules/merge-discipline.md` § "Coordinator-ack mechanics" for rationale (file markers were forgeable; commit status is not).
