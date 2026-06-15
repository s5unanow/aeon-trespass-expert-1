# 004 — CI speed: dependency caching (uv / pnpm / Playwright), concurrency-cancel, and pnpm version pinning

- **Priority:** P1 — recurring cost/latency on every push and PR
- **Effort:** S
- **Fix risk:** LOW
- **Dependency:** none
- **Category:** DX / CI efficiency
- **Planned-at commit:** `fc98b82`
- **Safety-gate scope:** **YES.** All edits are under `.github/workflows/`, which matches the safety-gate regex in `.claude/hooks/pre-pr-check.sh:242` (`^\.github/workflows/`). MUST ship via `/coordinator` with an adversarial-scenario plan in `tmp/plan-s5u-<N>.md` (CLAUDE.md step 3 + § "Safety-gate scope escalation"). Required-check **context names must not change** — `python / test`, `web / test`, `visual-regression / visual`, `visual-gate-scope / scan`, `coverage-table-scan / scan` are pinned in branch protection; run `make verify-branch-protection` after any workflow change.

## Why this matters

Verified at fc98b82: `grep -rn "cache" .github/workflows/` returns nothing. Every CI run, on every push:
- `python / test` re-resolves and downloads the full Python env (`uv sync`, no `enable-cache` on `astral-sh/setup-uv@v5`), then **also** installs Node + an **unpinned** pnpm (`npm install -g pnpm && pnpm install`) just to run the codegen-freshness check.
- `web / test` and `visual-regression / visual` each run a cold `pnpm install` (no `cache: 'pnpm'` on `setup-node`).
- `visual-regression / visual` downloads Chromium (~150 MB) from scratch (`playwright install --with-deps chromium`).
- `ci.yml` has no `concurrency` block, so rapid push-fix-push cycles (the norm under `scripts/run-issues.sh` autonomous loops) queue redundant full runs of the two longest jobs (`python / test` runs the full slow-inclusive pytest suite plus four repo-cloning harness scripts). Only `visual-regression.yml` and `coverage-table-scan.yml` define their own concurrency groups.
- The unpinned pnpm in `python-tests.yml` vs `version: 10` in the web workflows is a latent red-CI bomb: a pnpm major release changes lockfile semantics in `python / test` only.

Net effect: multiple minutes of pure setup per CI run and wasted runners on superseded commits — in a repo whose merge discipline requires waiting for CI on every PR *and* a green main-HEAD check before merge.

## Current state (verified at fc98b82)

`.github/workflows/python-tests.yml:19-28`:
```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: "latest"
      - name: Set up Python
        run: uv python install 3.12
      - name: Install dependencies
        run: uv sync
```
`.github/workflows/python-tests.yml:59-65`:
```yaml
      - name: Install Node (for TS codegen check)
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install pnpm
        run: npm install -g pnpm && pnpm install
```
`.github/workflows/web-tests.yml:12-23` and `visual-regression.yml:18-33`: `actions/setup-node@v4` with `node-version-file: '.nvmrc'` (no `cache:`), `pnpm/action-setup@v4` `version: 10`, `pnpm install`; visual-regression then `pnpm --filter @atr/web exec playwright install --with-deps chromium`.

`.github/workflows/ci.yml` (full file, 20 lines): four `uses:` job stanzas, no `concurrency:`. `visual-regression.yml:9-11` has its own `concurrency` (group `visual-regression-${{ github.ref }}`, `cancel-in-progress: true` unconditional). Root `package.json` has **no** `packageManager` field. `.nvmrc` = `20`.

## Repo conventions that bind this change

- Safety-gate scope: `/coordinator` shipping, coordinator-ack on HEAD, adversarial scenarios in `tmp/plan-s5u-<N>.md`.
- `.claude/rules/visual-verify.md` § "Adding a new top-level quality gate": no new required-check contexts here; if job/workflow *names* must change for any reason — don't. The reusable-workflow job names (`python / test` etc.) are load-bearing.
- `.claude/rules/guards.md` Rule G1: cache steps must not change guard semantics — caches are a pure speedup; a cache miss must behave identically to today (cold install).
- `scripts/check_post_merge_coordinator_ack.py` and `visual-gate-scope / scan` will scan the workflow diff — do not introduce any token matching the forbidden snapshot-update flags (`-u`, `--update-snapshots`, `--ignore-snapshots`) anywhere in workflow YAML, including in comments.
- Pure config change → no new tests required by the DoD (but workflow behavior must be verified on a real CI run before merge).

## Scope

**In scope:**
- `.github/workflows/python-tests.yml`
- `.github/workflows/web-tests.yml`
- `.github/workflows/visual-regression.yml`
- `.github/workflows/ci.yml`
- Root `package.json` (add `packageManager` field only)

**Explicitly out of scope:**
- Path-based job scoping / docs-only short-circuits (MED-risk with required checks; separate follow-up)
- `coverage-table-scan.yml`, `post-merge-coordinator-ack.yml`, `visual-gate-scope.yml` (no install steps worth caching; don't touch)
- Branch-protection settings themselves
- Any `scripts/check_*` guard

## Git workflow

1. File a Linear issue (ATE1/S5U); mark In Progress.
2. `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-ci-caching-concurrency`
3. Commits prefixed `S5U-XXX:`. **Ship via `/coordinator`. Do not push or open a PR unless the user instructs.**

## Ordered steps

### Step 0 — Adversarial plan (`tmp/plan-s5u-<N>.md`)

Scenarios to document:
- A1: poisoned/stale cache cannot mask a lockfile change — uv/pnpm cache keys include the lockfile hash; a `uv.lock`/`pnpm-lock.yaml` edit produces a fresh key.
- A2: cancel-in-progress must never cancel `main` push runs (post-merge audit + required main-HEAD green check depend on them) — guard with `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`.
- A3: Playwright cache key includes the Playwright version so a `@playwright/test` bump re-downloads browsers (stale browser + new runner = flaky visual diffs).
- A4: pnpm pin parity — all three workflows resolve the same pnpm major; `packageManager` field backstops local/dev drift.
- A5: `visual-regression.yml`'s existing unconditional `cancel-in-progress: true` also fires on `main` — decide deliberately whether to align it with the A2 guard in this PR (recommended: yes, same rationale) and document.

### Step 1 — uv cache in python-tests.yml

```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: "latest"
          enable-cache: true
          cache-dependency-glob: "uv.lock"
```
(`enable-cache` is the documented setup-uv option; it caches `~/.cache/uv` keyed on the dependency glob.)

### Step 2 — pnpm pin + caches in python-tests.yml

Replace the `npm install -g pnpm && pnpm install` step pair with the same pattern the web workflows use, plus the node cache:
```yaml
      - name: Install Node (for TS codegen check)
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'
      - name: Install pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 10
      - name: Install JS dependencies
        run: pnpm install
```
ORDERING NOTE: `setup-node` with `cache: 'pnpm'` requires pnpm to already be on PATH — put `pnpm/action-setup` **before** `setup-node` (this is the documented pattern). Mirror whichever order you use across all three workflows.

### Step 3 — pnpm cache in web-tests.yml and visual-regression.yml

Add `cache: 'pnpm'` to both `setup-node` steps (and reorder per the Step 2 note: `pnpm/action-setup@v4` first, then `setup-node`).

### Step 4 — Playwright browser cache in visual-regression.yml

Before the "Install Playwright browsers" step:
```yaml
      - name: Resolve Playwright version
        id: pw
        run: echo "version=$(node -p "require('@playwright/test/package.json').version")" >> "$GITHUB_OUTPUT"
        working-directory: apps/web
      - name: Cache Playwright browsers
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ runner.os }}-${{ steps.pw.outputs.version }}
```
Keep the `playwright install --with-deps chromium` step unchanged — on cache hit it verifies/installs OS deps quickly; on miss it downloads as today (G1: miss == current behavior).

### Step 5 — Concurrency on ci.yml

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```
Per A5, align `visual-regression.yml`'s group the same way (its current unconditional `cancel-in-progress: true` can cancel a main-push visual run). NOTE: `visual-regression.yml` is `workflow_call`-only — called from `ci.yml` — so once `ci.yml` has a top-level concurrency group, evaluate whether the child-level group is redundant or conflicting (two groups can deadlock-cancel; prefer the parent-level group and remove the child's, documenting in the adversarial plan).

### Step 6 — `packageManager` backstop

Add to root `package.json`: `"packageManager": "pnpm@10.x.y"` — use the exact version currently resolved in CI (check a recent CI log or `pnpm --version` locally) so `corepack`-aware environments agree with the workflows.

### Step 7 — Verify locally what's verifiable

```bash
uv run python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('YAML OK')"
make lint && make typecheck && make test     # full local gates (workflow files don't affect them, but DoD requires green)
make verify-branch-protection                 # expected-context derivation still matches live protection
```
Expected: `YAML OK`, gates green, branch-protection audit green.

### Step 8 — Coordinator shipping + real-CI verification

Ship via `/coordinator` (when the user instructs). After the PR's first CI run, verify in the run logs: uv cache hit/miss line, pnpm store cache restore, Playwright cache restore on a second push, and that a superseded push cancels the older non-main run. Compare wall-clock against a pre-change run and record the delta in the PR body.

## Test plan

- YAML validity (Step 7 command).
- `make verify-branch-protection` green before and after (context names untouched).
- On the PR's CI: second-push cache hits observed in logs for uv, pnpm, Playwright; superseded-push cancellation observed; `python / test` green with pinned pnpm 10.
- No new required-check contexts; `gh api repos/{owner}/{repo}/branches/main/protection/required_status_checks --jq '.contexts'` unchanged (read-only check).

## Machine-checkable done criteria

- [ ] `grep -n "enable-cache: true" .github/workflows/python-tests.yml` → match
- [ ] `grep -rn "npm install -g pnpm" .github/workflows/` → no matches
- [ ] `grep -cn "cache: 'pnpm'" .github/workflows/*.yml` → 3 matches (python-tests, web-tests, visual-regression)
- [ ] `grep -n "ms-playwright" .github/workflows/visual-regression.yml` → match
- [ ] `grep -n "concurrency:" .github/workflows/ci.yml` → match, with the main-branch guard expression
- [ ] `grep -n "packageManager" package.json` → match
- [ ] `make verify-branch-protection` → green
- [ ] All 5 required checks green on the PR; cache-hit lines present in the second CI run's logs

## STOP conditions

- STOP if `pnpm/action-setup` + `setup-node` ordering produces "Unable to locate executable file: pnpm" in CI — fix the order, don't drop the cache.
- STOP if the `ci.yml` concurrency group cancels a `main` push run in practice (check the expression evaluates as intended for `push` events on main) — required main-HEAD-green-before-merge and the post-merge coordinator-ack audit both depend on main runs completing.
- STOP if removing `visual-regression.yml`'s own concurrency block changes any behavior the S5U-599 enforcement stack documents as intentional (re-read the comment block at `visual-regression.yml:5-8` — it exists to prevent stale-run races on the required check); if in doubt, keep both groups but make the child's `cancel-in-progress` main-guarded too.
- STOP if `visual-gate-scope / scan` or `check_test_e2e_flags.sh` flags the diff — re-read the forbidden-token list; nothing in this plan should trip it, so a hit means an accidental token (likely in a comment).
- STOP if branch protection's expected contexts derived by `scripts/check_branch_protection.py` change — that script derives expectations from workflow files; renaming jobs/workflows is out of scope.

## Maintenance notes

- When `@playwright/test` is bumped, the browser cache key rolls automatically (version-derived) — no manual invalidation.
- When pnpm 11 releases, bump `version:` in all three workflows **and** `packageManager` in the same PR.
- The follow-up with the next-largest CI savings is docs-only path scoping (see plans/README.md) — implement with in-job change detection that still reports success, never `paths:` filters on required checks.
