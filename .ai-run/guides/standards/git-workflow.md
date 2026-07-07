# Git Workflow

Git workflow for Aeon Trespass Expert: branching, commits, pull requests, and merge policy.
All conventions below are hook-enforced (`.claude/hooks/pre-branch-check.sh`, `pre-commit-check.sh`, `pre-pr-check.sh`) — they are not aspirational.

## Branch Naming Convention

Pattern: `s5unanow/s5u-<issue-number>-<short-description>`

| Example | Notes |
|---|---|
| `s5unanow/s5u-1233-docs-only-ci-short-circuit` | Lowercase issue key in branch name |
| `s5unanow/s5u-997-ru-draft-edition-agy` | Short kebab-case description |

- Always branch from a fresh `main`: `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-short-description` (`AGENTS.md` § Development workflow step 2).
- Direct commits to `main` and dirty-tree-on-main are blocked by hook.

## Commit Message Format

Format: `S5U-<issue-number>: <description>` — the Linear issue key prefixes every commit.

| Example (from `git log`) | |
|---|---|
| `S5U-1233: docs-only PRs short-circuit the rendering CI jobs (in-job, fail-closed)` | |
| `S5U-1232: extract scripts/_git_baseline.py — dedup verify_ref_exists / get_changed_files` | |

- New/changed tests require a `Red-before confirmation:` line in the commit message or PR body — authoritative form in `.claude/rules/hooks.md` § "Three-input test discipline".
- The local quality gates run automatically on every `git commit` via the pre-commit hook. Never bypass hooks without disclosure (see `AGENTS.md` NEVER list).

## Merge Strategy

**Squash merge, one PR at a time**: `gh pr merge <pr-number> --squash --delete-branch` (`AGENTS.md` § Development workflow step 9).

Rationale: one Linear issue → one branch → one squashed commit on `main` keyed by the issue ID; keeps `main` history auditable against the tracker.

- Before merging, verify the latest CI run on `main` is green and its `headSha` matches current `main` HEAD; do not batch-merge.
- After merge: `git checkout main && git pull`, then move the Linear issue to Done.
- Rollback is always `git revert <merge-sha>` — never rewrite history on `main`.

## Anti-Patterns

| ❌ Avoid | ✅ Prefer |
|---|---|
| `git commit -m "fix stuff"` | `git commit -m "S5U-1234: fail closed on unresolvable base ref"` |
| Branch named `fix-bug` | `s5unanow/s5u-1234-fail-closed-base-ref` |
| Committing directly to `main` | Feature branch + PR (hook-blocked anyway) |
| `git push --force` / `git reset --hard` on `main` | `git revert <merge-sha>` + fix-forward PR |
| Merging with a red required check | Fix and push; `gh pr checks <pr> --watch` until green |
| Batch-merging several PRs back to back | Merge one, sync `main`, re-verify CI, then the next |

## Troubleshooting

| Symptom | Fix |
|---|---|
| Commit rejected by pre-commit hook | Run the failing gate locally (see `.ai-run/guides/quality-gates.md`), fix, re-commit. Do not use `--no-verify` without a PR-body disclosure (`.claude/rules/hooks.md` § "Hook-bypass disclosure"). |
| `gh pr create` refused on a safety-gate-scoped branch | Coordinator-ack commit status is required — see `AGENTS.md` § Development workflow step 6 and `.claude/rules/merge-discipline.md` § "Coordinator-ack mechanics". |
| Merge blocked on stale `main` SHA | Retry up to 3× with 10s delay; re-check `gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha'` (`AGENTS.md` § Development workflow step 9). |
| Visual-regression check red after an intentional UI change | Refresh baselines locally with `pnpm --filter @atr/web run test:visual:update` in a dedicated commit (`.claude/rules/visual-verify.md`). |
