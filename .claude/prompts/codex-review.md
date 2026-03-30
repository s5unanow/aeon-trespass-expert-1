# Codex Review Orchestration

You are managing a Codex code review session. Follow these steps exactly.

## 0. Extract context

```bash
git branch --show-current
```

Extract `S5U-<NUMBER>` from branch pattern `s5unanow/s5u-<NUMBER>-<description>`. Stop if on `main` or no valid issue ID.

## 1. Prerequisites

1. Verify codex is installed:
   ```bash
   which codex
   ```
   If not found: **STOP**. Print: "codex CLI not installed. Install via: `npm i -g @openai/codex`"

2. Verify all changes are committed (codex reviews the git state):
   ```bash
   git status --porcelain
   ```
   If dirty: **STOP**. Print: "Uncommitted changes detected. Commit before running Codex review."

3. Delete stale artifacts from previous runs:
   ```bash
   rm -f tmp/codex-review-s5u-<NUMBER>.md tmp/codex-input-s5u-<NUMBER>.md
   ```

## 2. Prepare input

Generate the diff and file list for context:

```bash
mkdir -p tmp
echo "## Changed files" > tmp/codex-input-s5u-<NUMBER>.md
git diff --stat main...HEAD >> tmp/codex-input-s5u-<NUMBER>.md
echo "" >> tmp/codex-input-s5u-<NUMBER>.md
echo "## Full diff" >> tmp/codex-input-s5u-<NUMBER>.md
git diff main...HEAD >> tmp/codex-input-s5u-<NUMBER>.md
```

## 3. Run the review

Run codex exec in read-only sandbox mode:

```bash
codex exec \
  -s read-only \
  -o tmp/codex-review-s5u-<NUMBER>.md \
  "You are reviewing a pull request for the Aeon Trespass Expert project. \
The diff is in tmp/codex-input-s5u-<NUMBER>.md. The codebase is available read-only. \
\
Focus your review on: \
1. Cross-subsystem contract integrity — data flows between pipeline (Python), schemas (Pydantic→TS), and web (React) must be consistent \
2. Type boundary mismatches — IR types, JSON schema, generated TS types must agree \
3. Export/render pipeline — if export changes, verify web still receives correct data shape \
4. Config consistency — TOML configs consumed by multiple subsystems must stay in sync \
5. Missing edge cases at subsystem boundaries \
\
End your review with exactly one of: \
VERDICT: APPROVED — no cross-system contract issues found \
VERDICT: REVISE — followed by a numbered list of specific issues to fix"
```

## 4. Parse the result

Read `tmp/codex-review-s5u-<NUMBER>.md` and search for the verdict:

- `VERDICT: APPROVED` → Codex review passed. Go to step 6.
- `VERDICT: REVISE` → Codex found issues. Go to step 5.
- Neither present → treat as REVISE (defensive).

## 5. REVISE loop (max 3 iterations)

Track iteration count. For each REVISE:

1. Read the issues Codex identified in `tmp/codex-review-s5u-<NUMBER>.md`
2. Fix the code (edit files, run affected tests)
3. Commit with prefix `S5U-<NUMBER>: address codex review feedback`
4. Resume the Codex session:
   ```bash
   codex exec resume --last \
     -o tmp/codex-review-s5u-<NUMBER>.md \
     "I have addressed your feedback. Please re-review the changes."
   ```
5. Parse the new output (same as step 4):
   - `VERDICT: APPROVED` → exit loop, go to step 6
   - `VERDICT: REVISE` → increment iteration count, repeat from substep 1

After 3 REVISE iterations without APPROVED:
- Save the latest Codex output as-is
- **STOP** and report: "Codex review did not converge after 3 rounds. Manual intervention needed. See tmp/codex-review-s5u-<NUMBER>.md"

## 6. Finalize artifact

After the review completes, prepend a YAML metadata header to the artifact file:

```yaml
---
codex_review: true
verdict: APPROVED | REVISE | INCOMPLETE
iterations: <N>
issue: S5U-<NUMBER>
---
```

Use the actual final verdict:
- `APPROVED` if Codex approved
- `REVISE` if stopped after max iterations (did not converge)
- `INCOMPLETE` if codex exec failed or produced no output

## 7. Post-loop cleanup

If any code was changed during the REVISE loop (step 5), the Claude review artifact (`tmp/review-s5u-<NUMBER>.md`) is stale. Delete it:

```bash
rm -f tmp/review-s5u-<NUMBER>.md
```

Report that Claude review must re-run before proceeding. The ship skill will handle re-running step 1.
