# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | Aeon Trespass Expert | `README.md:1`, `pyproject.toml:2` |
| Repository/package | aeon-trespass-expert (root `package.json`), `atr-schemas`/`atr-pipeline` (uv workspace members) | `package.json:2`, `pyproject.toml:12-19` |
| Project code/key | S5U (Linear team key; issues referenced as `S5U-NNNN`) | `CLAUDE.md` "Development workflow" §1, `git log --oneline -10` commit prefixes |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Linear |
| Key/prefix | S5U (team), project ATE1 |

> Adapter configuration belongs exclusively in `## Ticket Adapter`. Do not duplicate adapter status or instructions in the Work Item Tracker table.

## Ticket Adapter

**Status**: configured
**Adapter**: Linear is exposed via the `linear@claude-plugins-official` Claude Code plugin (`.claude/settings.json` `enabledPlugins.linear: true`), reached through MCP tool calls of the form `mcp__plugin_linear_linear__<tool>` (see `.claude/skills/next/SKILL.md:9`).
**Lookup**: Call `mcp__plugin_linear_linear__list_issues` with `project="ATE1"` and a `state` filter (e.g. `"Backlog"`) to list candidate issues; call the issue-detail equivalent tool with the issue ID for summary, description, acceptance criteria, and links.
**Create**: Call the plugin's issue-save tool with a complete issue payload (title, description, project, team) — never a conversational reference.
**Output**: Linear issue ID (e.g. `S5U-1471`) and its `linear.app` URL.

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | `https://github.com/s5unanow/aeon-trespass-expert-1.git` |
| Default target branch | `main` |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: `gh` CLI (`gh pr create`, `gh pr checks --watch`, `gh pr merge --squash --delete-branch`) — see `CLAUDE.md` §"Development workflow" steps 7-9.
**Instructions**: Link the Linear issue in the PR body; wait for CI green (`gh pr checks <pr-number> --watch`) before merge; verify `main` HEAD SHA matches the latest green CI run before merging (`CLAUDE.md` §9).
