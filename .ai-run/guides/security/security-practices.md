# Security Practices

This repo has no user-facing auth/authz surface (static reader + CLI pipeline). "Security" here means CI/safety-gate integrity, secret handling, and merge-discipline controls — the actual security-sensitive surface of an AI-assisted SDLC.

---

## Secret Guard (pre-commit Gate 0)

`.claude/hooks/pre-commit-check.sh` (`:99-133`) blocks staged secrets before any other gate runs:

| Blocked by filename | Blocked by content |
|---|---|
| `.env`, `*.key`, `*.pem`, `credentials.json` | `sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers |

---

## CI Guard Discipline (Rule G1 — fail-closed defaults)

Any CI guard (a script or workflow step that blocks merge on a condition) must exit non-zero on every degenerate input — missing base ref, `git diff`/`git show` failure, parse error, empty baseline, missing required env var. "Passes because the input state was absent" is a fail-open bug, not a pass. Concrete precedent: `check_extraction_scope.py` swallowed `git diff` errors into an empty list under shallow checkout, silently disabling a downstream guard (S5U-642). Full rule + required test coverage: `.claude/rules/guards.md` Rule G1.

## CI Guard Discipline (Rule G2 — content-derived, not name-derived)

A guard protecting a behavioral surface (snapshot updates, hook bypass, test skips) must detect the behavior by content inspection, not a hardcoded name list — a rename/wrapper/alias must not bypass it. Precedent: `check_visual_gate_scope.py` originally name-matched `test:visual:update`; a rename would have bypassed it (S5U-637). Full rule: `.claude/rules/guards.md` Rule G2.

---

## Hook-Bypass Disclosure

Any bypass of the pre-commit hook (`git commit --no-verify`/`-n`, `HUSKY=0`, `SKIP=`, hook-file mutation, `core.hooksPath` redirection) — even if rolled back before reaching `origin` — requires a `## Hook bypass disclosure` heading in the PR body naming the commit SHA, reason, and independent verification performed. Concealment grades as CRITICAL; disclosed bypass grades as WARNING. Full token enumeration: `.claude/rules/hooks.md` § "Hook-bypass disclosure".

---

## Admin-Merge Disclosure

Any merge that bypasses a branch-protection gate (`gh pr merge --admin`, REST merge with admin privilege, GitHub UI "merge without waiting") requires a `## Admin-merge disclosure` heading naming the bypassed surface, why it was appropriate, and independent verification. Full vector list and reviewer-probe semantics: `.claude/rules/merge-discipline.md` § "Admin-merge disclosure".

---

## Coordinator-Ack (safety-gate-scoped changes)

Changes to hooks, review gates, CI checks, merge guards, or `.claude/skills/**/SKILL.md` require a coordinator-ack GitHub commit status (not a worker-forgeable file marker) before `gh pr create` succeeds — enforced by `.claude/hooks/pre-pr-check.sh` and audited post-merge by `.github/workflows/post-merge-coordinator-ack.yml`. Signer allowlist: `.claude/coordinator-signers.txt`. Full mechanics: `.claude/rules/merge-discipline.md` § "Coordinator-ack mechanics".

---

## Secrets in Config

`.mcp.json` (local MCP server config, may hold credentials) is gitignored (`.gitignore`). Never commit `.env`, `.env.local`, or any file matching the Gate 0 patterns above.

---

## Quick Reference

| Need | Location |
|------|----------|
| Secret guard implementation | `.claude/hooks/pre-commit-check.sh` |
| CI guard fail-closed/content-derived rules | `.claude/rules/guards.md` |
| Hook-bypass disclosure | `.claude/rules/hooks.md` |
| Admin-merge / coordinator-ack | `.claude/rules/merge-discipline.md` |
