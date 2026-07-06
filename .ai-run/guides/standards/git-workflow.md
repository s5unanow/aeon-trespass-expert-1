# Git Workflow

Detected from `CLAUDE.md` §"Development workflow" and `git log --oneline -10` (commit prefixes match `S5U-\d+:` on every entry).

## Branch Naming Convention

Pattern: `s5unanow/s5u-<NUMBER>-<short-description>`

```
git checkout main && git pull && git checkout -b s5unanow/s5u-<NUMBER>-<short-description>
```

Branch naming, direct commits to `main`, and starting work from a dirty `main` tree are all mechanically enforced by `.claude/hooks/pre-branch-check.sh` (`CLAUDE.md` §"Development workflow" step 2).

## Commit Message Format

```
<issue-id>: <description>
```

**Example**: `S5U-1471: knowledge-foundation eval — Sonnet 5 @ xhigh` (matches real history, e.g. `1f377ca S5U-1233: docs-only PRs short-circuit the rendering CI jobs...`).

The 8 quality gates plus the secret guard run automatically on every commit via `.claude/hooks/pre-commit-check.sh`.

## Merge Strategy

**Squash merge**: `gh pr merge <pr-number> --squash --delete-branch` (`CLAUDE.md` §"Development workflow" step 9). Before merging, verify the latest CI run on `main` is green **and** its `headSha` matches current `main` HEAD (retry up to 3× with 10s delay on a stale SHA).

## Anti-Patterns

| Avoid | Prefer |
|---|---|
| `git commit --no-verify` / `-n` / `HUSKY=0` / `SKIP=` env-var bypasses without disclosure | Let the pre-commit hook run; if a bypass is genuinely required, add a `## Hook bypass disclosure` heading to the PR body (`.claude/rules/hooks.md`) |
| `git push --force` / `git reset --hard` on `main` | Feature branch + PR; `git revert <merge-sha>` for rollback (`CLAUDE.md` §"Rollback and emergency bypass") |
| `gh pr merge --admin` without disclosure | Add a `## Admin-merge disclosure` heading naming the bypassed surface, why it was appropriate, and how it was independently verified (`.claude/rules/merge-discipline.md`) |
| Committing directly to `main` | Feature branch named `s5unanow/s5u-<NUMBER>-<description>` |

## Troubleshooting

| Issue | Fix |
|---|---|
| Pre-commit hook blocks commit | Run `make check` locally to see which of the 9 gates failed; fix and re-commit — do not bypass without disclosure |
| CI red after push | Fix and push again; branch protection blocks merge on any red required check (`python / test`, `web / test`, `visual-regression / visual`, `visual-gate-scope / scan`, `coverage-table-scan / scan`) |
| Merge blocked on stale `main` SHA | Re-run `gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha'`, wait 10s, retry (up to 3×) |
