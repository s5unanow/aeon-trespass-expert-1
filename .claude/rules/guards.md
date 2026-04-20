---
description: CI guard discipline — fail-closed defaults and content-derived sets for safety-gate scripts and workflows
globs: scripts/check_*.py,scripts/check_*.sh,.github/workflows/**/*.yml,.github/actions/**/*.yml
---

# CI guard discipline

Two recurring failure modes have shown up across the repo's safety-gate CI guards in 2026-04 (see S5U-637 retrospective for a hardcoded-name bypass and S5U-642 for a shallow-checkout fail-open). This rule codifies the discipline that avoids them. Any new or modified safety-gate CI guard — a script, workflow step, or composite action whose role is "block merge when condition X holds" — must follow both rules.

## Rule G1 — fail-closed defaults

A CI guard must **exit non-zero with a clear message** in every degenerate-input case. A guard that "passes by virtue of absent state" is broken: an environment without the state the guard reads against (missing base ref, unresolvable `HEAD^`, shallow checkout, parse error on a required file, empty baseline map) is indistinguishable from "nothing to check" only if you wrote the guard to conflate the two.

### Degenerate cases a guard MUST treat as fail-closed

- **Missing base ref** — `git rev-parse --verify <base>^{commit}` fails, `git merge-base <base> HEAD` fails, or the ref simply wasn't fetched. Do not silently fall back to "no changes." Exit non-zero with a message like `"Base ref '<base>' is unresolvable — CI checkout likely shallow. Re-run with fetch-depth: 0 or pass --base explicitly."`.
- **`git diff` / `git show` subprocess failure** — non-zero exit from git. Do not return empty stdout or `None`. Exit non-zero with the captured stderr.
- **Parse error on a file the guard reads against** (TOML, JSON, YAML, package.json) — do not treat as "file missing"; a malformed file is a worse failure state than a missing one. Exit non-zero with the parse error line.
- **Empty baseline after diff / `git show`** — if the guard builds a baseline map from the base ref and it comes back empty when the head map is non-empty, **assume the base ref was unreadable**, not that every head entry is net-new. Exit non-zero unless the guard can independently verify "base legitimately had no entries" (e.g., file did not exist at the base commit, confirmed by `git cat-file -e`).
- **Required environment variable missing** — if the guard depends on `GITHUB_TOKEN`, `LINEAR_API_KEY`, `BASE_REF`, etc., exit non-zero with `"Missing required env var <name>; guard cannot verify and will fail closed."`. Do not default to permissive behavior.

### Required test coverage

Every G1 guard's test suite must include **at least one scenario that simulates a CI environment without the state the guard needs**. The minimum bar:

- A shallow-checkout scenario: set up a git repo with a single commit (or clone `--depth=1`) so the base ref is unresolvable. Run the guard. Assert exit code ≠ 0.
- A parse-error scenario: feed the guard a malformed TOML / JSON / YAML. Assert exit code ≠ 0 and the error message names the file and line.
- An empty-baseline scenario: seed the base commit with an empty file (or missing file) while the head commit has non-empty content. Assert the guard does not silently pass as "everything is net-new" — it either fails closed or emits a warning that is itself auditable.

These scenarios must be part of the guard's own test file (co-located with the script), not a downstream integration test that may be skipped in isolation.

### S5U-642 retrospective (the concrete failure this rule closes)

`check_extraction_scope.py` swallowed `git diff` errors into an empty list, and `check_threshold_changes.py::_git_show` returned `None` on `git show` failure. Net effect: a shallow-checkout CI run produced `changed_files = []`, which set `threshold_change_detected = false`, so the downstream guard was never invoked. When the guard *was* invoked, its empty baseline map made every head threshold look net-new, so no loosening was detected. A real threshold loosening silently passed CI. Both layers were independently fail-open; defense in depth failed because the whole stack had the same bug.

### Legitimate-override allowlist

Environment variables that *deliberately* enable permissive behavior — e.g., a `COVERAGE_BYPASS_REASON` env var that lets a guard emit a warning instead of failing — are allowed only when **both** of these hold:

1. The variable is set exclusively via a reviewer-visible GitHub Actions `if:` expression or a `workflow_dispatch` input, never a `secrets.*` reference or a worker-set env in a script.
2. The guard logs the override event with a SHA + issue reference so the bypass is audit-trailed.

An override that quietly flips the guard's default is itself a G1 violation.

## Rule G2 — content-derived sets over name-derived sets

For guards protecting **behavioral surfaces** — scripts that update snapshots, scripts that skip tests, commands that bypass hooks, workflow steps that modify protected state — the blocked set must be derived from **content inspection**, not a hardcoded list of names.

### What "content-derived" means

- **Content inspection**: parse `package.json` / `pyproject.toml` / workflow YAML, walk each script body / command, and detect the behavioral signature (e.g., "this command invokes Playwright with `--update-snapshots`"). The set of blocked scripts is whatever set matches the signature, computed at guard-run time.
- **Name-derived (the anti-pattern)**: `BLOCKED = {"test:visual:update"}` or `FORBIDDEN_SCRIPTS = ["test:visual:update", "test:visual-update"]`. Both are brittle — a rename (`test:visual-update`, `test:visual:refresh`, `e2e:update-baselines`) bypasses the guard.

### Required test coverage for G2 guards

Tests must include **rename, wrapper, and alias adversarial inputs**:

- **Rename**: a `package.json` script whose *name* is different from the canonical but whose *body* carries the forbidden flag (`"test:visual-update": "playwright test --update-snapshots"`). Assert the guard blocks it.
- **Wrapper**: a script that shells out to another script via `pnpm run <name>`, `bash -c …`, or an `npm_run_script` env trick, where the indirection ultimately invokes the forbidden flag. Assert the guard resolves the chain and blocks.
- **Alias**: a short-flag or aliased form (`-u` for `--update-snapshots`, `-n` for `--no-verify`, etc.). Paste the upstream tool's `--help` into the plan's "Tool surface citation" subsection to enumerate the aliases before writing the regex.

### Allowlist of hardcoded names

A hardcoded name list is allowed as **a fallback or legitimate-override allowlist**, never as the primary detector. The canonical pattern is:

```python
LOCAL_ONLY_SCRIPTS = frozenset({"test:visual:update"})  # reviewer-visible allowlist

def scan(package_json: dict) -> list[Violation]:
    tainted = {
        name
        for name, body in package_json["scripts"].items()
        if matches_forbidden_flag_pattern(body)   # content-derived
    }
    blocked = (tainted | LOCAL_ONLY_SCRIPTS) - legitimate_override_allowlist()
    ...
```

The allowlist says "these specific names are intentionally in scope even if they don't match the content pattern today" (e.g., a script whose body is a shell wrapper that will eventually invoke the flag). Any new script that matches the content pattern is added automatically without editing the allowlist.

### S5U-637 retrospective (the concrete failure this rule closes)

`check_visual_gate_scope.py` shipped S5U-611 with `LOCAL_ONLY_SCRIPTS = {"test:visual:update"}` as the **primary** detector. A hypothetical rename of `test:visual:update` to `test:visual-update` (with `playwright test --update-snapshots` preserved in the body) bypassed both the Python scanner and the `check_test_e2e_flags.sh` shell guard — neither derived "which scripts run `--update-snapshots`" from content; both name-matched. S5U-637 fixed this by computing `tainted` from the script bodies and extending the token-pattern match set to `LOCAL_ONLY_SCRIPTS ∪ tainted`.

## How to apply both rules

When writing a new guard:

1. Before coding, write a "degenerate inputs" section in `tmp/plan-s5u-<N>.md` §4 enumerating each G1 scenario for your guard (missing base ref, parse error, empty baseline, missing env var). For each, state the fail-closed exit behavior.
2. If the guard protects a behavioral surface (updates snapshots, skips tests, bypasses hooks, changes branch protection, etc.), write a "content signature" paragraph stating what behavioral pattern identifies an in-scope target (e.g., "any package.json script body matching regex `playwright\s+test\b.*--update-snapshots\b`").
3. Write tests that cover each G1 scenario *and* at least one G2 adversarial input (rename, wrapper, alias). Cite these tests in the plan and PR body.
4. If you fall back to a hardcoded allowlist, note why it's a fallback, not the primary detector. The PR body's "Semantically-equivalent threats" section must enumerate what the allowlist *doesn't* cover.

## Reviewer probe

`.claude/prompts/review.md` check #16 (safety gate bypass) calls out this rule explicitly. On any diff touching `scripts/check_*.py`, `scripts/check_*.sh`, or workflow `run:` steps that implement guard logic (including role-equivalent locations like `scripts/verify_*.py`, `scripts/validate_*.py`, composite actions under `.github/actions/**`), the reviewer must confirm:

- **G1**: every degenerate-input case (missing base ref, diff/`show` failure, parse error, empty baseline, missing env var) exits non-zero. The guard's test suite includes a shallow-checkout scenario.
- **G2**: the blocked set is content-derived, not name-derived. Tests cover rename / wrapper / alias inputs.

Findings are filed under check #16's CRITICAL severity (safety-gate bypass). A guard that violates G1 or G2 is a gate whose bypass the reviewer must call out by name.
