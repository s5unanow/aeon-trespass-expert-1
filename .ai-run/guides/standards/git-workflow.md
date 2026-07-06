# Git Workflow

Git conventions for Aeon Trespass Expert. Detected from `git log`, CLAUDE.md workflow steps 2/4/9, and `.claude/hooks/` (branch naming, direct-commit-to-main, and dirty-tree-on-main are hook-enforced).

## Branch Naming Convention

Pattern: `s5unanow/s5u-<NUMBER>-<short-description>` — the Linear issue id in lowercase, then a kebab-case slug.

```bash
git checkout main && git pull
git checkout -b s5unanow/s5u-1234-fix-render-cache
```

Examples: `s5unanow/s5u-1233-docs-short-circuit`, `s5unanow/s5u-1264-run-id-bound-render`.

Enforced by `.claude/hooks/pre-branch-check.sh`; commits directly to `main` are blocked.

## Commit Message Format

Format: `S5U-<NUMBER>: <imperative description>` — the Linear issue id as prefix, matching the branch's issue.

Examples from history:

- `S5U-1233: docs-only PRs short-circuit the rendering CI jobs (in-job, fail-closed)`
- `S5U-1232: extract scripts/_git_baseline.py — dedup verify_ref_exists / get_changed_files`

PRs that add new test functions must also carry a `Red-before confirmation:` line in the commit message or PR body (see `.claude/rules/hooks.md` § "Three-input test discipline").

The 9 local quality gates run automatically on every `git commit` via `.claude/hooks/pre-commit-check.sh` (< 60 s target). Never bypass them (`--no-verify`, `-n`, env-var bypasses, hook mutation) without a `## Hook bypass disclosure` section in the PR body — full contract in `.claude/rules/hooks.md`.

## Merge Strategy

Squash merge, feature branch deleted on merge:

```bash
gh pr merge <pr-number> --squash --delete-branch
git checkout main && git pull
```

Rationale: one Linear issue → one branch → one squashed commit on `main` keeps history 1:1 with the tracker. Before merging, verify the latest CI run on `main` is green and its `headSha` matches current main HEAD; never batch-merge, never merge red (branch protection blocks it). Rollback is always `git revert <merge-sha>` — never rewrite history on `main`.

## Anti-Patterns

| ❌ Avoid | ✅ Prefer |
|---|---|
| `git commit -m "fix stuff"` on main | `S5U-1234: <what changed>` on branch `s5unanow/s5u-1234-...` |
| `git push --force` / `git reset --hard` on main | `git revert <merge-sha>` + fix PR (CLAUDE.md NEVER list) |
| `git commit --no-verify` to dodge a failing gate | Fix the gate; if bypass is unavoidable, disclose per `.claude/rules/hooks.md` |
| Merging with a red required check via `--admin` | Wait for green; admin bypass requires `## Admin-merge disclosure` (`.claude/rules/merge-discipline.md`) |
| Batch-merging several PRs against a stale main | Merge one PR, sync main, re-verify CI, then the next |
| Branch without a Linear issue (`quick-fix`) | Create/pick the S5U issue first (CLAUDE.md workflow step 1) |

## Troubleshooting

| Symptom | Fix |
|---|---|
| Commit blocked by pre-commit hook | Run `make check` locally; the hook mirrors gates 1–8 plus the secret guard — fix the named failure, do not bypass |
| `gh pr create` refused with review-artifact error | The pre-PR hook (`.claude/hooks/pre-pr-check.sh`) requires `tmp/review-s5u-<N>.md`; run the fresh-eyes review first |
| `gh pr create` refused on a safety-gate-scoped branch | Coordinator-ack commit status missing — ship via `/coordinator` per CLAUDE.md step 6 |
| `git push` hangs | Credential-helper issue; push via `gh` auth (`git config credential.helper` → gh) |
| Merged the wrong thing | `git revert <merge-sha>`, push, open a fix PR, reopen the Linear issue |
