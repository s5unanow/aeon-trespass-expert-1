# 002 — Pre-commit hook fail-open fixes: amend bypasses the secret guard; hardcoded repo path; substring trigger

- **Priority:** P0 — integrity of the repo's first-line local gate
- **Effort:** S–M
- **Fix risk:** MED (trigger-regex tuning can false-positive/false-negative; the hook gates every commit)
- **Dependency:** none
- **Category:** safety-gate correctness
- **Planned-at commit:** `fc98b82`
- **Safety-gate scope:** **YES.** `.claude/hooks/pre-commit-check.sh` matches the safety-gate regex in `.claude/hooks/pre-pr-check.sh:242` (`^\.claude/hooks/`). Per CLAUDE.md § "Safety-gate scope escalation (MUST)" this MUST ship via `/coordinator` (coordinator-ack commit status on branch HEAD from a signer in `.claude/coordinator-signers.txt`), with adversarial scenarios documented in `tmp/plan-s5u-<N>.md`. Do NOT ship via `/ship`/`/next`/`/build-loop` as a lone worker.

## Why this matters

`.claude/hooks/pre-commit-check.sh` is the PreToolUse hook that enforces branch discipline, the secret guard, and the 8 quality gates on every `git commit` Claude runs. Three verified defects make it fail open (violating the repo's own `.claude/rules/guards.md` Rule G1/G2 — the exact discipline the repo's CI guards are held to):

1. **`--amend` skips the secret guard, not just the quality gates.** The amend early-exit sits *before* Gate 0 (secret/credential scan). An amend can stage arbitrary new content — including a fresh `.env` or an `sk-` key — and exits with zero scanning. The comment ("gates already passed on original commit") is wrong for newly staged content.
2. **Hardcoded repo path.** Line 11 `cd /Users/s5una/projects/aeon-trespass-expert-1` means in any git worktree or second clone the hook validates the *primary checkout's* tree, not the tree being committed: false-blocks (primary on `main` blocks all worktree commits via Guard 1) and fail-open (gates lint/test the primary's clean state while the worktree commits unvetted code). Worktrees are a live path here (spawned-task worktrees, coordinator sub-agents, `EnterWorktree`).
3. **Substring trigger.** Line 7 `grep -q 'git commit'` — any flag between `git` and `commit` (`git -C <path> commit`, `git --no-pager commit`, `git -c user.name=x commit`) defeats the literal match and silently skips branch guards, secret scan, and all gates. `.claude/rules/hooks.md` explicitly enumerates `git -c core.hooksPath=… commit` as a bypass vector, yet the enforcement hook name-matches its own front door. Inverse false positive: any Bash command merely containing the substring (e.g. writing a doc that mentions `git commit`) triggers the full multi-minute gate run.

## Current state (verified at fc98b82)

`.claude/hooks/pre-commit-check.sh:7-11`:
```bash
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'git commit'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-1
```

`.claude/hooks/pre-commit-check.sh:29-33` (before Gate 0 at lines 63-97):
```bash
# Skip quality gates for amend (minor fixups, gates already passed on original commit)
if echo "$CLAUDE_TOOL_INPUT" | grep -q -- '--amend'; then
  echo "Branch guards passed (skipping quality gates for amend)."
  exit 0
fi
```

Gate 0 (lines 63-97) scans staged filenames (`.env`, `*.key`, `*.pem`, `credentials.json`, …) and staged-diff content (`sk-`, `AKIA`, `ghp_`, `gho_`, PEM headers). Gates 1–8 run at lines 105-112.

Existing hook test suite: `apps/pipeline/tests/integration/test_hooks.py` (structural assertions: `test_all_python_gates_use_uv_run`, `test_gates_exit_on_failure`, `test_script_has_set_euo_pipefail`, etc.). Run via `make test-hooks`.

## Repo conventions that bind this change

- CLAUDE.md § "Safety-gate scope escalation" — `/coordinator` shipping path, coordinator-ack status, post-merge audit workflow re-checks `main`.
- CLAUDE.md step 3 — safety-gate changes require a plan with **adversarial scenarios** in `tmp/plan-s5u-<N>.md`; each scenario must hold or be fixed.
- `.claude/rules/hooks.md` — every shell command added/modified must be smoke-tested in a clean shell (`bash -c "..."`) and the test documented in the commit message or PR; any gating pattern-match needs ≥3 documented inputs (happy / failure / adversarial).
- `.claude/rules/guards.md` Rule G1 (fail-closed degenerate inputs) and G2 (content-derived over name-derived detection).
- New tests need `Red-before confirmation:` evidence.

## Scope

**In scope:**
- `.claude/hooks/pre-commit-check.sh`
- `apps/pipeline/tests/integration/test_hooks.py` (new structural/behavioral tests)
- `tmp/plan-s5u-<N>.md` (adversarial-scenario plan, gitignored)

**Explicitly out of scope:**
- `.claude/hooks/pre-pr-check.sh` (separate gate, separate issue if needed)
- Hook latency / pytest `slow`-marker work (separate finding; see plans/README.md)
- `.claude/settings.json` hook wiring
- Any `scripts/check_*.py` CI guard

## Git workflow

1. File a Linear issue (ATE1/S5U) describing the three fail-open vectors; mark In Progress.
2. `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-precommit-hook-fail-open`
3. Commits prefixed `S5U-XXX:`.
4. **Ship via `/coordinator`** — coordinator-ack status must exist on branch HEAD before `gh pr create` will be allowed by `pre-pr-check.sh`. Do not push or open a PR unless the user instructs.

## Ordered steps

### Step 0 — Adversarial plan (required for safety-gate scope)

Write `tmp/plan-s5u-<N>.md` enumerating at minimum these scenarios (each must hold post-fix):
- S1: `git commit --amend` staging a new file named `.env` → BLOCKED by Gate 0.
- S2: `git commit --amend` with no staged secrets → branch guards + Gate 0 pass, gates 1-8 skipped (preserved behavior).
- S3: `git -C /some/path commit -m x` → hook triggers (no silent skip).
- S4: `git --no-pager commit -m x` and `git -c core.hooksPath=/dev/null commit -m x` → hook triggers.
- S5: `echo "how to git commit" > notes.md` (Bash command that *mentions* but doesn't *run* commit) → hook does NOT trigger (FP check); document the residual: a command that both writes the string and commits still triggers — acceptable.
- S6: commit from a git worktree whose primary checkout is on `main` → hook runs against the worktree (no false block, gates see the worktree's staged tree).
- S7: `CLAUDE_TOOL_INPUT` unset/empty → hook exits 0 without error under `set -euo pipefail` (G1 check: confirm current behavior, keep it explicit).

### Step 1 — Red tests

Extend `apps/pipeline/tests/integration/test_hooks.py` with structural tests that read the hook source (matching the file's existing style):
- assert the `--amend` early-exit appears **after** the Gate 0 block (e.g. line-index comparison of `grep -n -- '--amend'` vs `Gate 0` marker), or better: a behavioral test that invokes the hook in a temp git repo (the file already has temp-repo harness patterns — reuse them) with an amend staging `.env` and asserts exit 1.
- assert the trigger line is not the literal `grep -q 'git commit'` substring match (e.g. the script contains the flag-tolerant pattern).
- assert no hardcoded `/Users/` path remains: `grep -c '/Users/' .claude/hooks/pre-commit-check.sh` == 0.

Verify (expected FAIL):
```bash
make test-hooks
```
Record red output + SHA for `Red-before confirmation:`.

### Step 2 — Fix the amend bypass

Move the amend check to *after* Gate 0: run Guard 1, Guard 2, then Gate 0 (secret scan) unconditionally, then skip gates 1-8 for amends. Keep the skip message accurate: `"Branch guards + secret scan passed (skipping quality gates 1-8 for amend)."`

Smoke test in a clean shell and document in the commit message:
```bash
CLAUDE_TOOL_INPUT='{"command":"git commit --amend"}' bash .claude/hooks/pre-commit-check.sh; echo "exit=$?"
```
(run inside a temp feature-branch repo with a staged `.env` → expect BLOCKED/exit 1; without secrets → expect exit 0 and gates skipped).

### Step 3 — Fix the hardcoded path

Replace line 11 with:
```bash
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
```
`CLAUDE_PROJECT_DIR` is set by the Claude Code harness for hooks; the `git rev-parse` fallback keeps the hook correct when invoked manually from anywhere inside a checkout. G1 note: if neither resolves (not in a repo), `git rev-parse` fails and `set -euo pipefail` aborts the hook non-zero — fail-closed, which is correct for a commit gate; document this in the adversarial plan.

### Step 4 — Fix the trigger match

Replace line 7's pattern with a flag-tolerant extended regex, e.g.:
```bash
if ! echo "$CLAUDE_TOOL_INPUT" | grep -qE '\bgit([[:space:]]+-[^[:space:]]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+commit\b'; then
```
Be careful: `git -c key=value commit` and `git -C path commit` have a *separated* argument after the flag — the regex above allows an optional argument token after each flag. Test all S3/S4/S5 inputs from the adversarial plan with the three-input discipline (`.claude/rules/hooks.md`), e.g.:
```bash
for c in 'git commit -m x' 'git -C /tmp commit' 'git --no-pager commit' 'git -c a=b commit' 'echo git commit docs' 'git status'; do
  printf '%s → ' "$c"; echo "{\"command\":\"$c\"}" | grep -qE '<pattern>' && echo MATCH || echo no-match
done
```
Expected: first four MATCH; note that `echo git commit docs` will also match any reasonable regex (the string contains `git … commit`) — that is the **pre-existing FP surface, unchanged**; the goal of this step is closing the FN vectors, not eliminating FPs. Document this explicitly in the PR body.

### Step 5 — Local gates + hook tests

```bash
make test-hooks                                    # new tests green
make lint && make typecheck && make test           # full gates green
```

### Step 6 — Coordinator shipping

Hand the branch to `/coordinator` for the worker/reviewer flow. The reviewer must walk `.claude/prompts/review.md` checks including #16 (safety-gate bypass, G1/G2 audit). Do not push or open a PR unless the user instructs.

## Test plan

- Behavioral: amend + staged `.env` → exit 1; amend clean → exit 0 with gates skipped; non-amend commit on `main` → blocked; worktree commit → operates on worktree.
- Structural: no `/Users/` literal; trigger regex matches the documented vector list; `--amend` check positioned after Gate 0.
- Three-input discipline documented inline for every changed pattern (happy / failure / adversarial), per `.claude/rules/hooks.md`.
- Full suite green (`make test`); CI `python / test` includes `test_hooks.py`.

## Machine-checkable done criteria

- [ ] `grep -c '/Users/' .claude/hooks/pre-commit-check.sh` → `0`
- [ ] `awk '/--amend/{a=NR} /Gate 0/{g=NR} END{exit !(a>g)}' .claude/hooks/pre-commit-check.sh` → exit 0 (amend check after Gate 0)
- [ ] `echo '{"command":"git -C /tmp commit -m x"}' | grep -qE '<final-pattern-from-hook>'` → match (and `git status` → no match)
- [ ] `make test-hooks` → green; `make lint && make typecheck && make test` → green
- [ ] `tmp/plan-s5u-<N>.md` exists with scenarios S1–S7 each marked HOLDS
- [ ] Coordinator-ack status (context `coordinator-ack`, state success) on branch HEAD before PR creation
- [ ] PR body documents smoke-test commands and the retained-FP note from Step 4

## STOP conditions

- STOP if `CLAUDE_TOOL_INPUT` turns out to be a JSON envelope whose `command` field needs proper extraction (e.g. flags split across JSON-escaped quotes) and the regex cannot be made reliable — escalate to parsing with `jq -r '.command'` first (check `jq` availability on this machine before relying on it; if unavailable, stop and surface options).
- STOP if any existing test in `test_hooks.py` encodes the current trigger string or hardcoded path as *desired* behavior — reconcile with the test author intent (git blame) before changing.
- STOP if the worktree fix (Step 3) breaks the harness invocation (hook runs with a cwd outside the repo and no `CLAUDE_PROJECT_DIR`) — verify how `.claude/settings.json` wires the hook before merging.
- STOP if you find yourself adding an env-var override to skip any part of this hook — that is a NEVER-list hook-bypass vector (S5U-629/S5U-672 retired exactly that pattern).

## Maintenance notes

- Any future edit to this hook re-enters safety-gate scope: coordinator shipping + adversarial plan, every time.
- The FP surface (commands that mention `git commit` without running it) is accepted; if it becomes noisy, the fix is `jq`-based command parsing, not loosening the match.
- Keep `scripts/test_hook_bypass_probes.sh` and the `hook_bypass.toml` corpus in mind: if the trigger change affects what the corpus considers a detectable bypass, the detector-corpus-coverage CI guard will demand a corpus diff.
