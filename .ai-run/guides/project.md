# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | aeon-trespass-expert | `pyproject.toml:2`, `package.json:2` |
| Repository/package | aeon-trespass-expert (root); `atr-pipeline` (apps/pipeline); `@atr/web` (apps/web); `@atr/schemas` (packages/schemas/ts) | `pyproject.toml`, `apps/pipeline/pyproject.toml:2`, `apps/web/package.json:2` |
| Project code/key | none | no separate internal project code found beyond the Linear tracker key below |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Linear |
| Key/prefix | S5U (team), project ATE1 |

> Adapter configuration belongs exclusively in `## Ticket Adapter`. Do not duplicate adapter status or instructions in the Work Item Tracker table.

## Ticket Adapter

**Status**: configured
**Adapter**: Linear MCP plugin (`linear@claude-plugins-official`, enabled in `.claude/settings.json`)
**Lookup**: Call `mcp__linear__get_issue` with the issue identifier, or `mcp__linear__list_issues(project="ATE1", state="Backlog")` to enumerate backlog issues
**Create**: Call `mcp__linear__save_issue` with the complete issue payload (title, description, `project="ATE1"`, team S5U)
**Output**: Linear issue identifier (e.g. `S5U-1476`) and URL returned by the MCP call

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | `https://github.com/s5unanow/aeon-trespass-expert-1.git` |
| Default target branch | main |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: GitHub CLI (`gh`)
**Instructions**: `gh pr create` with a summary and test plan, body following `.github/pull_request_template.md` (Linear issue link, Definition of Done checklist, Red-before confirmation). Safety-gate-scoped branches (hooks, review gates, CI checks, merge guards, `.claude/skills/**/SKILL.md`) require a `coordinator-ack` GitHub commit status on the branch HEAD before `gh pr create` succeeds — see `.ai-run/guides/security/security-practices.md`.
**Body Template**: `.github/pull_request_template.md`
