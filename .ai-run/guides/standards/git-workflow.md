# Git Workflow

Transcribed from `CLAUDE.md` § "Development workflow" and `.claude/rules/merge-discipline.md`, which remain the authoritative source — this guide exists so non-Claude-Code tooling can read the same conventions as data.

---

## Branch Naming Convention

Pattern: `s5unanow/s5u-<issue-number>-<short-description>`

Examples: `s5unanow/s5u-1476-kf2-sonnet`, `s5unanow/s5u-670-coordinator-ack`

```bash
git checkout main && git pull
git checkout -b s5unanow/s5u-<N>-<short-description>
```

Branch naming, direct commits to `main`, and a dirty tree on `main` are all enforced by `.claude/hooks/pre-branch-check.sh`.

---

## Commit Message Format

```
S5U-<N>: <description>
```

Example: `S5U-724: extract retrospective prose from CLAUDE.md into .claude/rules/`

The Linear issue ID prefix is mandatory and machine-checked by `.claude/hooks/pre-commit-check.sh`.

---

## Merge Strategy

**Squash merge**, branch deleted on merge:

```bash
gh pr merge <pr-number> --squash --delete-branch
```

Before merging: verify the latest CI run on `main` is green **and** its `headSha` matches current `main` HEAD (retry up to 3x with 10s delay on stale-SHA mismatch). Do not batch-merge multiple PRs without re-verifying between each.

After merge: `git checkout main && git pull`, then update the Linear issue to Done.

---

## Anti-Patterns

| ❌ Avoid | ✅ Instead | Why |
|----------|-----------|-----|
| Committing directly to `main` | Feature branch + PR | Enforced by pre-branch-check hook |
| `git commit --no-verify` undisclosed | Disclose bypass in PR body under `## Hook bypass disclosure` | Concealment is a CRITICAL finding, not the bypass itself |
| `gh pr merge --admin` undisclosed | Disclose under `## Admin-merge disclosure` naming bypassed surface + verification | Same concealment-is-worse framing |
| `git push --force` / `git reset --hard` on `main` | Never — use `git revert` for rollback | Irreversible history rewrite on shared branch |
| Merging with failing CI | Fix and re-push; wait for green | Branch protection blocks merge on any red required check |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Pre-commit hook fails | Fix the underlying issue; do not bypass without disclosure (`.claude/rules/hooks.md`) |
| `gh pr create` refused | Safety-gate-scoped branch missing `coordinator-ack` status — route through the `coordinator` workflow, not a lone `/ship` |
| Merge blocked despite green checks locally | `main` may have moved — re-verify `headSha` against current `main` HEAD before retrying |
| Stale CI run reported green | Re-fetch PR checks (`gh pr checks <n> --watch`); do not trust a cached status |

---

## Quick Reference

| Need | Location |
|------|----------|
| Full workflow (steps 1-9) | `CLAUDE.md` § "Development workflow" |
| Admin-merge / coordinator-ack mechanics | `.claude/rules/merge-discipline.md` |
| Hook-bypass disclosure | `.claude/rules/hooks.md` |
| Branch/commit enforcement | `.claude/hooks/pre-branch-check.sh`, `.claude/hooks/pre-commit-check.sh` |
