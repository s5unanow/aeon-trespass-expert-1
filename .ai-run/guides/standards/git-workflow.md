# Git Workflow

Branch, commit, and review conventions for aeon-trespass-expert. All work is tracked in Linear (project ATE1, team key `S5U`) and enforced by hooks under `.claude/hooks/`.

## Branch Naming Convention

Pattern: `s5unanow/s5u-<NNNN>-<short-description>`

| Example | Notes |
|---|---|
| `s5unanow/s5u-1477-knowledge-foundation-eval` | issue number + kebab description |
| `s5unanow/s5u-1231-make-check-aggregate` | one branch per Linear issue |

- Branch from an up-to-date `main`: `git checkout main && git pull && git checkout -b s5unanow/s5u-<NNNN>-<desc>`.
- Direct commits to `main`, dirty-tree-on-main, and off-pattern names are blocked by `.claude/hooks/pre-branch-check.sh`.

## Commit Message Format

Format: `S5U-<NNNN>: <description>`

| Example |
|---|
| `S5U-1233: docs-only PRs short-circuit the rendering CI jobs` |
| `S5U-1232: extract scripts/_git_baseline.py — dedup verify_ref_exists` |

Every commit references its Linear issue by the `S5U-<NNNN>:` prefix. The 9 local quality gates run automatically before each commit via `.claude/hooks/pre-commit-check.sh` (see `quality-gates.md`).

## Merge Strategy

**Squash merge** — `gh pr merge <pr> --squash --delete-branch`. One squashed commit per PR keeps `main` linear and one-issue-per-commit. Rationale: clean history aligned with the one-branch-per-issue model.

Before merging: confirm the latest CI run on `main` is green **and** its `headSha` matches current main HEAD; do not batch-merge. Sync after: `git checkout main && git pull`, then mark the Linear issue Done.

## Anti-Patterns

| ❌ Avoid | ✅ Instead |
|---|---|
| `git commit -m "fix stuff"` | `S5U-1477: fail-closed on unresolvable base ref` |
| Committing directly to `main` | Feature branch `s5unanow/s5u-<NNNN>-<desc>` |
| `git commit --no-verify` (silent) | Let hooks run; if ever bypassed, add a `## Hook bypass disclosure` (`.claude/rules/hooks.md`) |
| `git reset --hard` / `git push --force` on `main` | Never — use `git revert` for rollbacks |
| Merging with a red required check | Fix and push; branch protection blocks red merges |

## Troubleshooting

| Issue | Fix |
|---|---|
| Pre-commit hook blocks the commit | Read the failing gate output; fix, or if bypass was truly unavoidable, disclose per `.claude/rules/hooks.md` |
| Branch name rejected | Match `s5unanow/s5u-<NNNN>-<desc>` |
| Stale-SHA on merge | Re-check `gh api repos/{owner}/{repo}/branches/main --jq '.commit.sha'`; retry up to 3× with 10s delay |
| Safety-gate-scoped PR blocked at `gh pr create` | Ship via `/coordinator` (needs a `coordinator-ack` status) — `.claude/rules/merge-discipline.md` |

## References

- Full workflow (pick issue → PR → merge → sync): `CLAUDE.md` "Development workflow (MANDATORY)".
- Linear issue conventions: `.claude/prompts/linear-conventions.md`.
- Merge discipline / admin-bypass disclosure: `.claude/rules/merge-discipline.md`.
