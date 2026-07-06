# Git Workflow

Branching, commits, PRs, and merge policy for aeon-trespass-expert. Work is tracked in
Linear (team **S5U**, project **ATE1**). Branch naming, direct-commit-to-main blocks, and
dirty-tree checks are enforced by `.claude/hooks/pre-branch-check.sh` and
`.claude/hooks/pre-commit-check.sh`.

## Branch Naming Convention

**Pattern**: `s5unanow/s5u-<NNNN>-<short-description>`

| Example | Notes |
|---|---|
| `s5unanow/s5u-1233-docs-only-ci-shortcircuit` | issue number + kebab description |
| `s5unanow/s5u-690-make-doc-parity` | |

Create from an up-to-date main:
```bash
git checkout main && git pull && git checkout -b s5unanow/s5u-<NNNN>-<desc>
```
Never commit directly to `main` (hook-enforced).

## Commit Message Format

**Format**: `S5U-<NNNN>: <description>`

| Example |
|---|
| `S5U-1233: docs-only PRs short-circuit the rendering CI jobs` |
| `S5U-1232: extract scripts/_git_baseline.py — dedup verify_ref_exists` |

The `S5U-` prefix referencing the Linear issue is mandatory on every commit. The 9 local
pre-commit gates run automatically before each commit via the hook — do not bypass them
(see Anti-Patterns).

## Merge Strategy

**Squash merge**, delete the branch after merge:
```bash
gh pr merge <pr-number> --squash --delete-branch
git checkout main && git pull
```
Rationale: one Linear issue → one squashed commit on `main` keeps history linear and each
`S5U-` change atomic and revertible. Rollback is `git revert <merge-sha>` (never rewrite
history on main).

## Merge Preconditions

- CI green — all required checks pass (branch protection blocks red merges).
- Before `gh pr merge`, verify the latest `main` CI run is green **and** its `headSha`
  matches current main HEAD; retry on stale-SHA. Do not batch-merge.
- Safety-gate-scoped changes require a coordinator-ack (see `.claude/rules/merge-discipline.md`).

## Anti-Patterns

| ❌ DON'T | ✅ DO |
|---|---|
| `git commit -m "fix stuff"` | `S5U-1234: fail loud not silent in PDF extract` |
| Commit straight to `main` | Branch `s5unanow/s5u-<NNNN>-...` first |
| `git commit --no-verify` / `HUSKY=0` silently | If ever bypassed, add a `## Hook bypass disclosure` (`.claude/rules/hooks.md`) |
| `git reset --hard` / `git push --force` on main | `git revert <sha>` for rollback |
| `gh pr merge --admin` silently | Disclose under `## Admin-merge disclosure` (`.claude/rules/merge-discipline.md`) |
| Merge with red or stale-SHA CI | Confirm green + matching `headSha` first |

## Troubleshooting

| Symptom | Fix |
|---|---|
| Commit rejected: not on a feature branch | You're on `main`; create `s5unanow/s5u-<NNNN>-...` |
| Commit rejected: missing `S5U-` prefix | Amend the message to `S5U-<NNNN>: ...` |
| Pre-commit gate fails | Run `make check` locally; fix, don't `--no-verify` |
| `git push` hangs (osxkeychain) | Uses `gh` credential helper — see repo setup notes |
| Merge blocked by branch protection | A required check is red; fix and push, never `--admin` without disclosure |

## References

- Full workflow contract: `AGENTS.md` and `.claude/rules/merge-discipline.md`
- Linear conventions: `.claude/prompts/linear-conventions.md`
- Quality gates run per commit: `.ai-run/guides/quality-gates.md`
