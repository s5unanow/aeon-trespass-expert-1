# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | Aeon Trespass Expert | CLAUDE.md:1 |
| Repository/package | aeon-trespass-expert-1 | git remote, CLAUDE.md:1 |
| Project code/key | S5U | CLAUDE.md:80 (Linear team S5U) |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Linear |
| Key/prefix | S5U |

> Adapter configuration belongs exclusively in `## Ticket Adapter`. Do not duplicate adapter status or instructions in the Work Item Tracker table.

## Ticket Adapter

**Status**: configured
**Adapter**: mcp__claude_ai_Linear__list_issues, mcp__claude_ai_Linear__save_issue (Linear MCP)
**Lookup**: mcp__claude_ai_Linear__get_issue(issue_id="{ticket_id}") — returns summary, description, acceptance criteria, and linked artifacts
**Create**: mcp__claude_ai_Linear__save_issue(title="{title}", description="{description}", team_id="S5U", project_id="ATE1") — pass complete story payload
**Output**: Linear issue ID (S5U-XXXX) and URL

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | https://github.com/s5unanow/aeon-trespass-expert-1.git |
| Default target branch | main |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: gh (GitHub CLI) — create PR via `gh pr create`, list checks via `gh pr checks`, merge via `gh pr merge`
**Instructions**: Use `gh pr create --base main --title "..." --body "..."` after pushing branch. Link Linear issue in PR body. Merge with `gh pr merge <pr-number> --squash --delete-branch` after CI green. Branch protection enforces 18 quality-gate contexts before merge is permitted.
