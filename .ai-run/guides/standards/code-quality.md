# Code Quality Standards

Lint, format, type, and structural standards. Exact run commands live in
`.ai-run/guides/quality-gates.md`; this guide is the *what and why*.

## Python

| Standard | Tool / setting | Source |
|---|---|---|
| Lint rule set | ruff `select = [E,F,W,I,UP,B,SIM,RUF,C901,PLR0912,PLR0913,PLR0915]` | `pyproject.toml:40` |
| Complexity | McCabe `max-complexity = 12` | `pyproject.toml:43` |
| Function shape | `max-args = 7`, `max-branches = 12`, `max-statements = 50` | `pyproject.toml:46` |
| Formatting | `ruff format` (line length 100) | `pyproject.toml:35` |
| Types | `mypy --strict` (no unjustified `Any`) | `pyproject.toml:74` |
| Import layers | import-linter "Pipeline layer contract" | `pyproject.toml:94` |
| File length | ≤ 400 lines (`check_file_length.py`) | `.claude/rules/pipeline.md` |

Per-file ruff ignores are tracked to issues, not scattered silently — see the
`[tool.ruff.lint.per-file-ignores]` block at `pyproject.toml:51` (each carries an `S5U-`
reference). Follow that pattern: justify any new ignore with a tracking issue.

## TypeScript

| Standard | Tool / setting | Source |
|---|---|---|
| Lint | oxlint with import plugin | `apps/web/package.json` (`lint`) |
| No import cycles | `import/no-cycle: error` | `apps/web/.oxlintrc.json` |
| File length | `max-lines: 400` (blank/comment-skipping) | `apps/web/.oxlintrc.json` |
| Unused vars | `no-unused-vars: warn` (`^_` ignored) | `apps/web/.oxlintrc.json` |
| Types | `tsc --noEmit` | `apps/web/package.json` (`typecheck`) |
| Formatting | prettier | `apps/web/package.json` (`format`) |

## Schemas — generated, never hand-written

Contract direction is one-way: Python Pydantic → JSON Schema → TypeScript. Never edit
`packages/schemas/jsonschema/` or `packages/schemas/ts/`; change the Pydantic source and run
`make codegen`. Freshness is CI-gated by `check_codegen_fresh.sh` / `make check-codegen`
(`.claude/rules/schemas.md`).

| Avoid | Prefer |
|---|---|
| Editing a generated `.ts` / `.json` schema file | Edit `packages/schemas/python/*` then `make codegen` |
| A ruff ignore with no rationale | A per-file ignore tied to an `S5U-` issue (`pyproject.toml:51`) |
| A 401-line source file | Split it; the gate blocks growth of grandfathered files |

## Do / Don't

| ✅ DO | ❌ DON'T |
|---|---|
| Keep functions under the ruff complexity/shape caps | Suppress C901/PLR without a tracked issue |
| Run `make lint` before pushing | Rely on local green alone (CI has extra gates) |
| Regenerate schemas after model changes | Commit drifted generated schemas |
