# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | Aeon Trespass Expert | README.md:1 |
| Repository/package | aeon-trespass-expert (uv workspace) / @atr/* (pnpm workspace) | package.json:2, pyproject.toml:2 |
| Project code/key | S5U (Linear team), project ATE1 | git log commit prefixes; CLAUDE.md workflow |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Linear |
| Key/prefix | S5U |

> Adapter configuration belongs exclusively in `## Ticket Adapter`. Do not duplicate adapter status or instructions in the Work Item Tracker table.

## Ticket Adapter

**Status**: configured
**Adapter**: Linear MCP server (Linear plugin enabled in `.claude/settings.json`); call the `mcp__linear__*` tools directly.
**Lookup**: Call `mcp__linear__get_issue` with the issue id (e.g. S5U-1234) to get title, description, acceptance criteria, and links; `mcp__linear__list_issues` with project ATE1 to enumerate.
**Create**: Call `mcp__linear__save_issue` with the complete issue payload (team S5U, project ATE1, title, full description) — never a conversational reference to a prior draft.
**Output**: Linear issue identifier (S5U-NNN) and issue URL returned by the tool.

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | https://github.com/s5unanow/aeon-trespass-expert-1.git |
| Default target branch | main |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: GitHub CLI (`gh`)
**Instructions**: Push the feature branch, then create the PR with `gh pr create` linking the Linear issue in the body. A mandatory independent fresh-eyes review precedes every PR, and safety-gate-scoped branches additionally require a coordinator-ack commit status — see `.ai-run/guides/standards/development-workflow.md` and CLAUDE.md. Merge is squash via `gh pr merge --squash --delete-branch` only after all required CI checks are green.
**Body Template**: `.github/pull_request_template.md`
