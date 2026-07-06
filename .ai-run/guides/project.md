# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | Aeon Trespass Expert | README.md:1, CLAUDE.md |
| Repository/package | aeon-trespass-expert (monorepo: `atr-pipeline`, `@atr/web`, `@atr/schemas`) | apps/pipeline/pyproject.toml:2, apps/web/package.json:2 |
| Project code/key | ATE1 (Linear project; team S5U) | CLAUDE.md "project ATE1, team S5U" |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Linear |
| Key/prefix | S5U |

## Ticket Adapter

**Status**: configured
**Adapter**: Call the Linear MCP tools `mcp__claude_ai_Linear__*` (server enabled via `linear@claude-plugins-official`, `.claude/settings.json:3`).
**Lookup**: Call `mcp__claude_ai_Linear__get_issue` with `id=<ticket-id>` (e.g. `S5U-1472`) to retrieve summary, description, acceptance criteria, and links.
**Create**: Call `mcp__claude_ai_Linear__save_issue` with the complete work-item payload (`team=S5U`, `project=ATE1`, title, description) — pass the full story, never a conversational reference.
**Output**: Linear issue identifier (`S5U-<NNNN>`) and issue URL returned by the tool.

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | https://github.com/s5unanow/aeon-trespass-expert-1.git |
| Default target branch | main |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: `gh` CLI — `gh pr create --base main --title "S5U-<NNNN>: <desc>" --body "<body>"`; merge with `gh pr merge <n> --squash --delete-branch`.
**Instructions**: Commit and branch conventions are in `.ai-run/guides/standards/git-workflow.md`. Link the Linear issue in the PR body. Do not merge on red or stale-SHA CI. Safety-gate-scoped changes require a coordinator-ack (`.claude/rules/merge-discipline.md`).
