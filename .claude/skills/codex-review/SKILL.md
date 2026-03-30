---
name: codex-review
description: Run a Codex cross-system code review. Use when user says "codex review", "second review", or for cross-system changes.
---

# Codex code review

## 0. Extract issue context

```bash
git branch --show-current
```

Extract `S5U-<NUMBER>` from branch pattern `s5unanow/s5u-<NUMBER>-<description>`. Stop if on `main` or no valid issue ID.

## 1. Write marker file

```bash
mkdir -p tmp
touch tmp/.codex-required-s5u-<NUMBER>
```

This signals to the pre-PR hook that Codex review was requested.

## 2. Run Codex review

Read `.claude/prompts/codex-review.md` and follow its instructions. The orchestration handles prerequisites, the review invocation, and the full REVISE loop.

## 3. Report result

- **APPROVED** → "Codex review passed. Ready for PR."
- **APPROVED after N rounds** → "Codex review passed after N revision rounds."
- **INCOMPLETE** → "Codex review did not converge. See tmp/codex-review-s5u-<NUMBER>.md for details."
