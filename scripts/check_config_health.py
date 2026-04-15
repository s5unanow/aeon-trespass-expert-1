#!/usr/bin/env python3
"""Check configuration health: detect drift across CLAUDE.md, hooks, skills, and CI.

Verifies path integrity, gate count consistency, skill directory sync,
and hook registration. Outputs pass/fail report with file:line references.

Usage:
    python scripts/check_config_health.py
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

Finding = tuple[str, str, str]  # (level, location, message)

_SKIP_PREFIXES = (
    "http://",
    "https://",
    "git ",
    "make ",
    "uv ",
    "uv run ",
    "pnpm ",
    "npm ",
    "cd ",
    "rm ",
    "find ",
    "grep ",
    "bash ",
    "mcp__",
    "gh ",
    "S5U-",
    "ruff ",
    "mypy ",
    "oxlint",
    "tsc ",
    "pytest",
    "lint-",
    "node ",
)


_PATH_PREFIXES = (
    "apps/",
    "packages/",
    "scripts/",
    "configs/",
    "docs/",
    "artifacts/",
    ".claude/",
    ".github/",
    ".agents/",
)


def _iter_section_lines(text: str, section_heading: str) -> Iterator[str]:
    """Yield markdown lines under the named heading until the next peer heading."""
    in_section = False
    section_level = 0
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if not in_section:
            if lower.startswith("#") and section_heading.lower() in lower:
                in_section = True
                section_level = len(stripped) - len(stripped.lstrip("#"))
            continue
        if stripped.startswith("#"):
            heading_level = len(stripped) - len(stripped.lstrip("#"))
            if heading_level <= section_level:
                break
        yield line


def _looks_like_path(token: str) -> bool:
    """Heuristic: does this backtick token look like a file/directory path?"""
    if any(token.lower().startswith(p) for p in _SKIP_PREFIXES):
        return False
    if token.startswith("-"):
        return False
    if any(c in token for c in ("&&", "||", "|", ";", ">", "<", "$", "(", ")")):
        return False
    if "/" not in token:
        return False
    # Must start with a known repo directory or relative path prefix
    return any(token.startswith(p) for p in _PATH_PREFIXES)


def _extract_inline_paths(text: str) -> list[tuple[int, str]]:
    """Extract path-like tokens from inline backtick spans outside code blocks."""
    results: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in re.finditer(r"`([^`]+)`", line):
            token = match.group(1).strip()
            if _looks_like_path(token):
                path_str = token.rstrip("/")
                results.append((i, path_str))
    return results


def _glob_base_path(root: Path, path_str: str) -> Path:
    """Return the literal prefix before any glob metacharacters."""
    glob_chars = "*?["
    first_glob = min((path_str.find(char) for char in glob_chars if char in path_str), default=-1)
    literal_prefix = path_str if first_glob == -1 else path_str[:first_glob]
    return root / literal_prefix.rstrip("/")


def check_path_references(root: Path) -> list[Finding]:
    """Verify file paths referenced in config markdown files exist."""
    findings: list[Finding] = []

    md_files: list[Path] = []
    for name in ("CLAUDE.md", "AGENTS.md"):
        p = root / name
        if p.exists():
            md_files.append(p)

    for subdir in (".claude/skills", ".claude/rules", ".claude/prompts"):
        d = root / subdir
        if d.exists():
            md_files.extend(d.rglob("*.md"))

    checked = 0
    for md_file in md_files:
        text = md_file.read_text()
        rel_md = str(md_file.relative_to(root))

        for line_num, path_str in _extract_inline_paths(text):
            if any(x in path_str for x in ("XXX", "<", ">", "example")):
                continue

            if any(char in path_str for char in "*?["):
                target = _glob_base_path(root, path_str)
            else:
                target = root / path_str

            if target.exists():
                checked += 1
                continue
            checked += 1
            findings.append(("FAIL", f"{rel_md}:{line_num}", f"path not found: {path_str}"))

    if not findings:
        print(f"  \u2713 Path references ({len(md_files)} files, {checked} paths)")
    return findings


def _count_numbered_items(text: str, section_heading: str) -> int:
    """Count numbered list items under a markdown section.

    Respects heading hierarchy: only stops at headings of the same level
    or higher than the matched section, not at deeper subsections.
    """
    count = 0
    for line in _iter_section_lines(text, section_heading):
        stripped = line.strip()
        if re.match(r"^\d+\.", stripped):
            count += 1
    return count


def _section_contains(text: str, section_heading: str, pattern: str) -> bool:
    """Return whether the named markdown section contains the given regex."""
    section_lines = _iter_section_lines(text, section_heading)
    return any(re.search(pattern, line, re.IGNORECASE) for line in section_lines)


def _hook_has_secret_guard(text: str) -> bool:
    """Detect the dedicated secret-guard check in the pre-commit hook."""
    return bool(
        re.search(r"Gate 0: .*secret guard", text, re.IGNORECASE)
        or re.search(r"\[\d+/\d+\]\s+secret guard", text, re.IGNORECASE)
    )


def check_gate_consistency(root: Path) -> list[Finding]:
    """Verify documented local checks and executable quality gates stay aligned."""
    findings: list[Finding] = []
    claude_total_checks: int | None = None
    claude_quality_gates: int | None = None
    hook_total_checks: int | None = None
    hook_quality_gates: int | None = None
    preflight_quality_gates: int | None = None

    # CLAUDE.md lists gates under ### Local subsection.
    # AGENTS.md is a compatibility shim — it does not list gates.
    p = root / "CLAUDE.md"
    if p.exists():
        claude_text = p.read_text()
        claude_total_checks = _count_numbered_items(claude_text, "local")
        secret_guard_count = 1 if _section_contains(claude_text, "local", r"secret guard") else 0
        claude_quality_gates = claude_total_checks - secret_guard_count

    hook = root / ".claude" / "hooks" / "pre-commit-check.sh"
    if hook.exists():
        text = hook.read_text()
        hook_quality_gates = len(re.findall(r"run_gate\s+", text))
        hook_total_checks = hook_quality_gates + int(_hook_has_secret_guard(text))

    preflight = root / ".claude" / "skills" / "preflight" / "SKILL.md"
    if preflight.exists():
        text = preflight.read_text()
        preflight_quality_gates = _count_numbered_items(text, "gates")

    if (
        claude_total_checks is not None
        and hook_total_checks is not None
        and claude_total_checks != hook_total_checks
    ):
        findings.append(
            (
                "FAIL",
                "gate consistency",
                "local pre-commit check mismatch — "
                f"CLAUDE.md total: {claude_total_checks}, "
                f".claude/hooks/pre-commit-check.sh total: {hook_total_checks}",
            )
        )

    if (
        claude_quality_gates is not None
        and preflight_quality_gates is not None
        and claude_quality_gates != preflight_quality_gates
    ):
        findings.append(
            (
                "FAIL",
                "gate consistency",
                "quality gate mismatch — "
                f"CLAUDE.md executable gates: {claude_quality_gates}, "
                f".claude/skills/preflight/SKILL.md gates: {preflight_quality_gates}",
            )
        )

    if (
        hook_quality_gates is not None
        and preflight_quality_gates is not None
        and hook_quality_gates != preflight_quality_gates
    ):
        findings.append(
            (
                "FAIL",
                "gate consistency",
                "quality gate mismatch — "
                f".claude/hooks/pre-commit-check.sh run_gate count: {hook_quality_gates}, "
                f".claude/skills/preflight/SKILL.md gates: {preflight_quality_gates}",
            )
        )

    if not findings:
        surfaces = sum(
            value is not None
            for value in (claude_total_checks, hook_total_checks, preflight_quality_gates)
        )
        if surfaces:
            quality_gate_count = next(
                value
                for value in (hook_quality_gates, preflight_quality_gates, claude_quality_gates)
                if value is not None
            )
            summary = f"{quality_gate_count} quality gates"
            if claude_total_checks is not None and hook_total_checks is not None:
                extra_checks = hook_total_checks - quality_gate_count
                summary += f" + {extra_checks} additional pre-commit check"
                if extra_checks != 1:
                    summary += "s"
            print(f"  \u2713 Gate consistency ({summary} across {surfaces} surfaces)")

    return findings


def check_skill_sync(root: Path) -> list[Finding]:
    """Detect duplicate .agents/ directory alongside .claude/."""
    findings: list[Finding] = []

    agents_dir = root / ".agents"
    claude_dir = root / ".claude"

    if agents_dir.exists() and claude_dir.exists():
        findings.append(
            (
                "FAIL",
                ".agents/",
                "duplicate directory: both .agents/ and .claude/ exist",
            )
        )
    else:
        print("  \u2713 Skill directory sync (no duplicates)")

    return findings


def check_hook_registration(root: Path) -> list[Finding]:
    """Verify hooks in settings.json exist and are executable."""
    findings: list[Finding] = []

    settings_path = root / ".claude" / "settings.json"
    if not settings_path.exists():
        findings.append(("FAIL", ".claude/settings.json", "settings file not found"))
        return findings

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        findings.append(("FAIL", ".claude/settings.json", f"invalid JSON: {exc}"))
        return findings

    hooks = settings.get("hooks", {})
    checked = 0
    for event_name, hook_list in hooks.items():
        for i, entry in enumerate(hook_list):
            for j, hook in enumerate(entry.get("hooks", [])):
                if hook.get("type") != "command":
                    continue
                cmd = hook.get("command", "")
                script_path = cmd.split()[0] if cmd else ""
                if not script_path:
                    continue

                full_path = root / script_path
                loc = f".claude/settings.json (hooks.{event_name}[{i}].hooks[{j}])"
                checked += 1

                if not full_path.exists():
                    findings.append(("FAIL", loc, f"script not found: {script_path}"))
                elif not full_path.stat().st_mode & 0o111:
                    findings.append(("FAIL", loc, f"script not executable: {script_path}"))

    if not findings:
        print(f"  \u2713 Hook registration ({checked} hooks)")

    return findings


def main() -> int:
    root = Path(__file__).resolve().parent.parent

    print("Config Health Report")
    print("=" * 40)

    all_findings: list[Finding] = []

    checks = [
        ("Path references", check_path_references),
        ("Gate consistency", check_gate_consistency),
        ("Skill directory sync", check_skill_sync),
        ("Hook registration", check_hook_registration),
    ]

    for name, check_fn in checks:
        findings = check_fn(root)
        if findings:
            print(f"\n  \u2717 {name}:")
            for level, loc, msg in findings:
                print(f"    {level}  {loc}: {msg}")
            all_findings.extend(findings)

    print()
    fails = [f for f in all_findings if f[0] == "FAIL"]
    if fails:
        print(f"{len(fails)} issue(s) detected.")
        return 1

    print("All config health checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
