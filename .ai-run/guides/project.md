# Project Context

## Project Identity

| Field | Value | Source |
|---|---|---|
| Project name | Aeon Trespass Expert | `README.md:1` |
| Repository/package | `aeon-trespass-expert` (repo `s5unanow/aeon-trespass-expert-1`) | `package.json:2`, `git remote -v` |
| Project code/key | ATE1 (Linear project), team S5U | `AGENTS.md` § Development workflow |

## Work Item Tracker

| Field | Value |
|---|---|
| Provider | Linear |
| Key/prefix | S5U |

> Adapter configuration belongs exclusively in `## Ticket Adapter`. Do not duplicate adapter status or instructions in the Work Item Tracker table.

## Ticket Adapter

**Status**: configured
**Adapter**: Linear MCP server (`claude.ai Linear`), enabled via the `linear` plugin in `.claude/settings.json:3`. Invoke its MCP tools directly.
**Lookup**: Call the Linear MCP `get_issue` tool with the issue identifier (e.g. `S5U-1234`) to retrieve summary, description, acceptance criteria, and links; use `list_issues` filtered by project `ATE1` to find work.
**Create**: Call the Linear MCP `save_issue` tool with the complete issue payload (title, full description with acceptance criteria, team `S5U`, project `ATE1`) — never a conversational reference to earlier drafts.
**Output**: Linear issue identifier (`S5U-NNNN`) and issue URL returned by the tool.

## Source Control And Review

| Field | Value |
|---|---|
| Provider | GitHub |
| Repository remote | `https://github.com/s5unanow/aeon-trespass-expert-1.git` |
| Default target branch | `main` |
| Review artifact type | PR |

## MR Adapter

**Status**: configured
**Adapter**: GitHub CLI (`gh`): `gh pr create` to open, `gh pr checks --watch` to monitor CI, `gh pr merge --squash --delete-branch` to merge.
**Instructions**: PRs must link the Linear issue in the body. Repo hooks enforce a pre-PR review-artifact contract on local `gh pr create` (see `AGENTS.md` § Development workflow step 6). Never merge with failing CI; branch protection blocks red required checks.
**Body Template**: Summary + test plan + Linear issue link, per `.github/pull_request_template.md`.
