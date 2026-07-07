# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | Aeon Trespass Expert | README.md:1 |
| Repository/package | aeon-trespass-expert | package.json:2 |
| Project code/key | ATE1 (Linear project) | CLAUDE.md development-workflow section |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Linear |
| Key/prefix | S5U |

> Adapter configuration belongs exclusively in `## Ticket Adapter`. Do not duplicate adapter status or instructions in the Work Item Tracker table.

## Ticket Adapter

**Status**: configured
**Adapter**: Invoke the Linear MCP tools (`mcp__claude_ai_Linear__*`) via the tool interface; the Linear plugin is enabled in `.claude/settings.json`.
**Lookup**: Call `mcp__claude_ai_Linear__get_issue` with `id=<S5U-NNNN>` to return summary, description, acceptance criteria, and links; use `mcp__claude_ai_Linear__list_issues` with `project="ATE1"` to enumerate.
**Create**: Call `mcp__claude_ai_Linear__save_issue` with a complete issue payload (title, description, team `S5U`, project `ATE1`); pass the full payload, never a conversational reference.
**Output**: Linear issue identifier (`S5U-NNNN`) and issue URL returned by the tool.

> **Schema enforcement:** The `## Ticket Adapter` section MUST contain only these five fields: `**Status**`, `**Adapter**`, `**Lookup**`, `**Create**`, `**Output**`. Never add extra fields. Phase 5 validates this.

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | https://github.com/s5unanow/aeon-trespass-expert-1.git |
| Default target branch | main |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: GitHub CLI (`gh pr create`, `gh pr checks`, `gh pr merge --squash --delete-branch`).
**Instructions**: Push the branch (`git push -u origin HEAD`), open the PR with a summary + test plan, and link the Linear issue in the body. Wait for all required CI checks green before merge; never merge red. See `standards/git-workflow.md`.
