# Git Workflow

## Quick Summary

Git workflow for Aeon Trespass Expert: branching, commits, pull requests, and code review. Mandatory workflow: Linear issue → branch → plan (if cross-subsystem) → code → review → PR → merge.

**Category**: Standards
**Complexity**: Simple
**Prerequisites**: Git basics, Linear account access

---

## Branch Naming Convention

**Pattern**: `s5unanow/s5u-<NUMBER>-<short-description>`

**Examples**:
- `s5unanow/s5u-1233-docs-only-prs-short-circuit-rendering`
- `s5unanow/s5u-1470-kf-haiku`

**Rule**: Branch name must include the Linear issue ID (S5U-XXXX). Direct commits to `main` are blocked by hook.

---

## Workflow

```bash
# 1. Create branch from clean main
git checkout main
git pull
git checkout -b s5unanow/s5u-<NUMBER>-description

# 2. Code & commit with prefix
git add [files]
git commit -m "S5U-<NUMBER>: description"

# 3. Push
git push -u origin HEAD

# 4. Create PR via CLI
gh pr create --base main --title "S5U-<NUMBER>: title" --body "..."
```

---

## Commit Message Format

**Format**: `<issue-id>: <description>`

**Examples**:
- `S5U-1233: docs-only PRs short-circuit the rendering CI jobs`
- `S5U-1232: extract scripts/_git_baseline.py`

**Rule**: Commit prefix is **mandatory**. The 9 local pre-commit gates run automatically before each commit via hook.

---

## Commit Rules

| ✅ DO | ❌ DON'T |
|-------|----------|
| Prefix all commits with S5U-XXXX | Commit directly to main |
| Atomic, well-scoped changes | Mix unrelated changes in one commit |
| Link the Linear issue in PR body | Omit context or issue reference |
| Run `make check` before push | Skip lint/test gates |

---

## Pull Request

### PR Title

Format: `S5U-<NUMBER>: <short-title>`

### PR Body

Required sections:
1. **Summary** — 1–3 bullets describing what changed and why
2. **Test plan** — checklist of manual/automated verification
3. **Linear link** — paste the issue URL

**Example**:
```markdown
S5U-1233: docs-only PRs short-circuit rendering CI

## Summary
- Mark docs-only PRs with a label so CI jobs skip unnecessary rendering
- Reduces pipeline runtime by 10–15 minutes per PR
- One-line filter in `.github/workflows/ci.yml`

## Test plan
- [ ] Pushed docs-only PR and verified rendering jobs skipped
- [ ] Pushed code PR and verified rendering jobs ran

Link: https://linear.app/s5una/issue/S5U-1233
```

---

## Code Review

**Mandatory**: One fresh-eyes review before merge. Review path is determined by whether the `Agent` tool is available:

- **Path A** (top-level): Spawn independent sub-agent review using `.claude/prompts/review.md` (25-point probe).
- **Path B** (sub-agent fallback): Inline self-review walking all 25 checks; disclose the fallback in PR body.

**Safety-gate scope hard-stop**: If PR touches `.claude/hooks/`, `.claude/skills/`, `.claude/prompts/review.md`, `.github/workflows/`, or `CLAUDE.md`, it MUST ship via `/coordinator` skill (not `/ship`). See CLAUDE.md § "Step 6" for details.

---

## Merge Strategy

**Strategy**: Squash + delete branch

```bash
# After CI green and review approved
gh pr merge <pr-number> --squash --delete-branch
```

**Branch protection**: 18 required-check contexts must be `success` before merge is permitted. CI green is the definition of done.

---

## Quality Gates

**Local** (pre-commit hook, ~60 s target):
1. Secret guard (blocks .env, *.key, API keys)
2. ruff check (lint, McCabe complexity max 12)
3. ruff format --check (format violations)
4. mypy --strict (type errors)
5. import-linter (no cyclic imports)
6. file-length (max 400 lines per source file)
7. oxlint (frontend lint)
8. tsc --noEmit (frontend types)
9. pytest fast subset (unit tests, no timeouts)

**CI** (9 extra gates on push/PR): codegen, fixtures, extraction scope, visual regression, visual-gate-scope, coverage table, instruction drift, make/doc parity.

See `.ai-run/guides/quality-gates.md` for full gate list and exact commands.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Commit rejected by pre-commit hook | Run `make check` to see which gate failed; fix and re-commit |
| PR blocked by required checks | Check `gh pr checks <pr-number> --watch`; fix failing gates locally and push |
| Can't merge due to branch protection | Ensure all 18 required checks are `success`; do not use admin-merge without `## Admin-merge disclosure` in PR body (see CLAUDE.md § NEVER) |
| Accidentally committed to main | Run `git reset --hard origin/main` to discard (destructive, only if not pushed) |
| Need to revert a merged PR | `git revert <merge-sha>`, push, open new fix PR, reopen the Linear issue |

---

## References

- **Branch pattern source**: CLAUDE.md:87
- **Development workflow**: CLAUDE.md:78–120
- **Safety rules**: CLAUDE.md:154–176 (NEVER list)
- **Quality gates**: `.ai-run/guides/quality-gates.md`
