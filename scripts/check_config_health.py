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
    "eslint",
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
            target = root / path_str
            if target.exists():
                checked += 1
                continue
            if any(x in path_str for x in ("XXX", "<", ">", "example")):
                continue
            checked += 1
            findings.append(("FAIL", f"{rel_md}:{line_num}", f"path not found: {path_str}"))

    if not findings:
        print(f"  \u2713 Path references ({len(md_files)} files, {checked} paths)")
    return findings


def _count_numbered_items(text: str, section_heading: str) -> int:
    """Count numbered list items under a markdown section."""
    in_section = False
    count = 0
    for line in text.splitlines():
        lower = line.lower().strip()
        if section_heading.lower() in lower and lower.startswith("#"):
            in_section = True
            continue
        if in_section:
            if re.match(r"^\d+\.", line.strip()):
                count += 1
            elif line.strip().startswith("#"):
                break
    return count


def check_gate_consistency(root: Path) -> list[Finding]:
    """Verify gate count matches across CLAUDE.md, AGENTS.md, hook, preflight."""
    findings: list[Finding] = []
    gate_counts: dict[str, int] = {}

    for name in ("CLAUDE.md", "AGENTS.md"):
        p = root / name
        if p.exists():
            gate_counts[name] = _count_numbered_items(p.read_text(), "quality gates")

    hook = root / ".claude" / "hooks" / "pre-commit-check.sh"
    if hook.exists():
        text = hook.read_text()
        gate_counts[".claude/hooks/pre-commit-check.sh"] = len(re.findall(r"run_gate\s+", text))

    preflight = root / ".claude" / "skills" / "preflight" / "SKILL.md"
    if preflight.exists():
        text = preflight.read_text()
        gate_counts[".claude/skills/preflight/SKILL.md"] = len(
            re.findall(r"^###\s+\d+\.", text, re.MULTILINE)
        )

    if gate_counts:
        values = set(gate_counts.values())
        if len(values) > 1:
            detail = ", ".join(f"{k}: {v}" for k, v in sorted(gate_counts.items()))
            findings.append(("FAIL", "gate consistency", f"gate count mismatch — {detail}"))
        else:
            count = next(iter(values))
            surfaces = len(gate_counts)
            print(f"  \u2713 Gate consistency ({count} gates across {surfaces} surfaces)")

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
