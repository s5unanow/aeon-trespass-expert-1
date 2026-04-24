---
description: Visual verification rules for rendering changes — applies to web components, styles, routes, export scripts, and render stages
globs: apps/web/src/components/**,apps/web/src/routes/**,apps/web/src/styles/**,scripts/export_to_web.py,scripts/_export_blocks.py,apps/pipeline/src/atr_pipeline/stages/render/**
---

When working on changes that affect page rendering (web components, CSS, pipeline render/export stages, facsimile overlays), verify the result visually before creating a PR:

1. Ensure the dev server is running on `localhost:3001`
2. Use Playwright MCP to navigate to affected pages:
   - `mcp__playwright__browser_navigate` to `http://localhost:3001/documents/ato_core_v1_1/{edition}/{pageId}`
3. Take a screenshot with `mcp__playwright__browser_take_screenshot` (fullPage, savePng to `tmp/`)
4. Read the screenshot to visually confirm the change looks correct
5. If interactive elements exist, use `mcp__playwright__browser_hover` or `mcp__playwright__browser_click` to verify they work
6. Use `mcp__playwright__browser_evaluate` to inspect DOM state when needed

This applies to files matching:
- `apps/web/src/components/**`
- `apps/web/src/routes/**`
- `apps/web/src/styles/**`
- `scripts/export_to_web.py`
- `scripts/_export_blocks.py`
- `apps/pipeline/src/atr_pipeline/stages/render/**`

## Updating visual-regression baselines

If your change legitimately alters the rendered output of a curated page covered by `apps/web/tests/e2e/__snapshots__/`, the CI `visual-regression` gate will fail until the baseline is refreshed. Regenerate locally and commit the diff:

```
pnpm --filter @atr/web run test:visual:update
```

Inspect the regenerated PNGs, commit them in a dedicated commit (`S5U-XXX: refresh visual baselines — <reason>`), and explain each refresh in the PR body. CI is blocked from regenerating baselines itself — see "Visual regression CI gate (S5U-599)" below.

## Visual regression CI gate (S5U-599)

The short-form rule in `CLAUDE.md` names the gate and its 0.005 threshold.
This section holds the full enforcement-stack history and the operational
detail the reviewer agent and branch-protection operators need.

### Baselines

Baselines live at `apps/web/tests/e2e/__snapshots__/*.png` and are committed
to git. They are the ground truth; every PR is diffed against them.

### Threshold

`maxDiffPixelRatio: 0.005` (0.5% of pixels may differ). Configured centrally
in `apps/web/playwright.config.ts`. Do not loosen without a linked issue
explaining why. Avoid per-test overrides; if you need one, justify in the PR.

### Intentional baseline update (legitimate UI change)

Run `pnpm --filter @atr/web run test:visual:update` locally, inspect the
regenerated PNGs under `apps/web/tests/e2e/__snapshots__/`, and commit the
diff in a dedicated commit (`S5U-XXX: refresh visual baselines — <why>`). The
reviewer must confirm the visual delta is intentional.

### CI never regenerates baselines — two-layer enforcement

1. **Job-local guard (S5U-611 hardened)** — `scripts/check_test_e2e_flags.sh`
   in `.github/workflows/visual-regression.yml` fails the job if
   `apps/web/package.json`'s `test:e2e` script contains `-u`,
   `--update-snapshots`, or `--ignore-snapshots`, **and also** fails the job
   if any `.github/workflows/*.yml` or `.github/actions/**/*.yml` names one
   of those flags on a `run:` line. This keeps the required-check-side
   fallback effective even if the separate scope-scan job is renamed,
   deleted, or taken out of `required_status_checks.contexts`.
2. **Scope-scan job (S5U-608, hardened S5U-611)** — the separate
   `visual-gate-scope / scan` job (`scripts/check_visual_gate_scope.py`)
   scans every workflow/action YAML and every package.json script for those
   flags, and blocks any workflow `run:` line that names
   `test:visual:update` as a word-bounded token (under any package-manager
   invocation surface, including bare `pnpm <script>` — S5U-611). The legacy
   `# visual-gate-scope: allow` marker is no longer a valid exemption inside
   `.github/**`; appearing there is itself a violation (S5U-611 Gap 2).

Do not add the forbidden flags to any CI command under any circumstance. See
S5U-608 for the original threat model and `tmp/plan-s5u-611.md` for the Gap
1/2/3 adversarial matrix.

### Adding a new top-level quality gate — branch-protection append rule

Any new required-check-style job (Python/JS scanner, YAML linter, etc.)
MUST be added to branch protection's `required_status_checks.contexts` in
the same PR that introduces the workflow.

**Warning — `PATCH .../required_status_checks` and `PUT
.../required_status_checks/contexts` both REPLACE the full context list;
passing a single `contexts[]=<name>` wipes out every other required check.**

Use the **append-only** endpoint `POST
/repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks/contexts`
— e.g.:

```bash
gh api -X POST repos/{owner}/{repo}/branches/main/protection/required_status_checks/contexts \
  -f 'contexts[]=<new-check-name>'
```

Verify with:

```bash
gh api repos/{owner}/{repo}/branches/main/protection/required_status_checks --jq '.contexts'
```

before and after; the new name should be present alongside `python / test`,
`web / test`, `visual-regression / visual`, `visual-gate-scope / scan`, and
`coverage-table-scan / scan`.

If you actually need PATCH (e.g., to toggle `strict`), read-modify-write the
full union first:

```bash
current=$(gh api repos/{owner}/{repo}/branches/main/protection/required_status_checks --jq '[.contexts[]]')
gh api -X PATCH repos/{owner}/{repo}/branches/main/protection/required_status_checks \
  --input <(jq -n --argjson c "$current" '{strict:true, contexts: ($c + ["<new-check-name>"] | unique)}')
```

**Never a bare `-f 'contexts[]=<single>'` against PATCH/PUT.** This was the
latent gap in S5U-608 that S5U-611 closed — a job wired into `ci.yml` but
absent from `contexts` is one-diff-away from being silently removed (and the
original example for this step was itself destructive; see S5U-639).

### Live branch-protection audit (S5U-709)

Run `make verify-branch-protection` after any PR-facing workflow change or any
manual GitHub protection edit. The audit derives the expected required-check
contexts from the repo workflow files, then compares that set against the
live `main` branch protection and fails if `required_status_checks.strict`
or `enforce_admins.enabled` drift. As of S5U-709 the expected blocking
contexts are `python / test`, `web / test`, `visual-regression / visual`,
`visual-gate-scope / scan`, and `coverage-table-scan / scan`.

### Adding new curated pages

Add a `toHaveScreenshot('page-id.png')` assertion in
`apps/web/tests/e2e/*.spec.ts`, generate the baseline locally via
`test:visual:update`, and commit both the spec change and the PNG.

### Platform note

Baselines are captured on the Linux CI runner. On macOS/Windows dev machines,
anti-aliasing and font hinting typically produce 2–4% pixel drift even
without code changes, which will exceed the 0.005 threshold. This is
expected. The authoritative run is CI. When you refresh baselines locally to
push an intentional UI change, CI will re-verify them on Linux; if they fail
on CI, pull the refreshed PNGs from the CI test-results artifact and commit
those instead.
