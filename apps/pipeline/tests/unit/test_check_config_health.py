"""Tests for scripts/check_config_health.py config drift detection."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_config_health.py"


@pytest.fixture()
def health_module() -> Iterator[ModuleType]:
    """Import check_config_health.py as a module."""
    spec = importlib.util.spec_from_file_location("check_config_health", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_config_health"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_config_health", None)


@pytest.fixture()
def healthy_repo(tmp_path: Path) -> Path:
    """Create a minimal repo structure that passes all checks."""
    (tmp_path / "CLAUDE.md").write_text(
        "## Quality gates\n\n### Local\n1. ruff check\n2. ruff format\n3. mypy\n"
    )
    (tmp_path / "AGENTS.md").write_text(
        "# AGENTS.md — Compatibility Shim\n\nCanonical instructions live in CLAUDE.md.\n"
    )
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(json.dumps({"hooks": {}}))
    return tmp_path


# -- Path reference checks --


class TestPathReferences:
    def test_missing_path_detected(self, health_module: ModuleType, healthy_repo: Path) -> None:
        (healthy_repo / "CLAUDE.md").write_text("See `.claude/prompts/review.md` for details\n")
        findings = health_module.check_path_references(healthy_repo)
        assert len(findings) == 1
        assert findings[0][0] == "FAIL"
        assert ".claude/prompts/review.md" in findings[0][2]

    def test_existing_path_passes(self, health_module: ModuleType, healthy_repo: Path) -> None:
        prompts = healthy_repo / ".claude" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "review.md").write_text("review prompt")
        (healthy_repo / "CLAUDE.md").write_text("See `.claude/prompts/review.md` for details\n")
        findings = health_module.check_path_references(healthy_repo)
        assert findings == []

    def test_non_path_backtick_ignored(self, health_module: ModuleType, healthy_repo: Path) -> None:
        (healthy_repo / "CLAUDE.md").write_text("Use `ruff check` and `import/no-cycle` rule\n")
        findings = health_module.check_path_references(healthy_repo)
        assert findings == []

    def test_code_block_paths_ignored(self, health_module: ModuleType, healthy_repo: Path) -> None:
        (healthy_repo / "CLAUDE.md").write_text("```bash\nuv run scripts/nonexistent.py\n```\n")
        findings = health_module.check_path_references(healthy_repo)
        assert findings == []

    def test_placeholder_paths_ignored(self, health_module: ModuleType, healthy_repo: Path) -> None:
        (healthy_repo / "CLAUDE.md").write_text("Branch: `apps/<component>/src`\n")
        findings = health_module.check_path_references(healthy_repo)
        assert findings == []


# -- Gate consistency checks --


class TestGateConsistency:
    def test_matching_counts_pass(self, health_module: ModuleType, healthy_repo: Path) -> None:
        findings = health_module.check_gate_consistency(healthy_repo)
        assert findings == []

    def test_mismatch_detected(self, health_module: ModuleType, healthy_repo: Path) -> None:
        """Hook gate count differs from CLAUDE.md → mismatch."""
        hooks_dir = healthy_repo / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-commit-check.sh").write_text('run_gate "a" cmd\nrun_gate "b" cmd\n')
        findings = health_module.check_gate_consistency(healthy_repo)
        assert len(findings) == 1
        assert "mismatch" in findings[0][2]
        assert "CLAUDE.md: 3" in findings[0][2]
        assert "pre-commit-check.sh: 2" in findings[0][2]

    def test_nested_subsections_counted(
        self, health_module: ModuleType, healthy_repo: Path
    ) -> None:
        """Numbered items under ### subsections are counted correctly."""
        (healthy_repo / "CLAUDE.md").write_text(
            "## Quality gates\n\n"
            "### Local (pre-commit hook, 8 gates)\n\n"
            "1. ruff check\n"
            "2. ruff format\n"
            "3. mypy\n\n"
            "### CI (3 extra)\n\n"
            "4. codegen check\n"
            "5. fixture check\n"
            "## Next section\n"
        )
        findings = health_module.check_gate_consistency(healthy_repo)
        # CLAUDE.md counts under ### Local = 3 — no other surfaces → pass
        assert findings == []

    def test_preflight_gates_counted(self, health_module: ModuleType, healthy_repo: Path) -> None:
        """Preflight SKILL.md gates are counted via numbered items under ## Gates."""
        preflight_dir = healthy_repo / ".claude" / "skills" / "preflight"
        preflight_dir.mkdir(parents=True)
        (preflight_dir / "SKILL.md").write_text(
            "# Preflight\n\n## Gates\n\n1. ruff check\n2. ruff format\n3. mypy\n\n## Reporting\n"
        )
        findings = health_module.check_gate_consistency(healthy_repo)
        # All surfaces now have 3 → match
        assert findings == []

    def test_hook_gate_count_included(self, health_module: ModuleType, healthy_repo: Path) -> None:
        hooks_dir = healthy_repo / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-commit-check.sh").write_text(
            'run_gate "a" cmd\nrun_gate "b" cmd\nrun_gate "c" cmd\n'
        )
        findings = health_module.check_gate_consistency(healthy_repo)
        # 3 gates in hook matches 3 in CLAUDE.md → pass
        assert findings == []


# -- Skill sync checks --


class TestSkillSync:
    def test_no_agents_dir_passes(self, health_module: ModuleType, healthy_repo: Path) -> None:
        findings = health_module.check_skill_sync(healthy_repo)
        assert findings == []

    def test_duplicate_dirs_detected(self, health_module: ModuleType, healthy_repo: Path) -> None:
        (healthy_repo / ".agents").mkdir()
        findings = health_module.check_skill_sync(healthy_repo)
        assert len(findings) == 1
        assert "duplicate" in findings[0][2]


# -- Hook registration checks --


class TestHookRegistration:
    def test_missing_hook_detected(self, health_module: ModuleType, healthy_repo: Path) -> None:
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": ".claude/hooks/missing.sh",
                            }
                        ],
                    }
                ]
            }
        }
        (healthy_repo / ".claude" / "settings.json").write_text(json.dumps(settings))
        findings = health_module.check_hook_registration(healthy_repo)
        assert len(findings) == 1
        assert "not found" in findings[0][2]

    def test_non_executable_hook_detected(
        self, health_module: ModuleType, healthy_repo: Path
    ) -> None:
        hooks_dir = healthy_repo / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        script = hooks_dir / "test.sh"
        script.write_text("#!/bin/bash\nexit 0\n")
        os.chmod(script, 0o644)

        settings = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": ".claude/hooks/test.sh",
                            }
                        ],
                    }
                ]
            }
        }
        (healthy_repo / ".claude" / "settings.json").write_text(json.dumps(settings))
        findings = health_module.check_hook_registration(healthy_repo)
        assert len(findings) == 1
        assert "not executable" in findings[0][2]

    def test_valid_hooks_pass(self, health_module: ModuleType, healthy_repo: Path) -> None:
        hooks_dir = healthy_repo / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        script = hooks_dir / "test.sh"
        script.write_text("#!/bin/bash\nexit 0\n")
        os.chmod(script, 0o755)

        settings = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": ".claude/hooks/test.sh",
                            }
                        ],
                    }
                ]
            }
        }
        (healthy_repo / ".claude" / "settings.json").write_text(json.dumps(settings))
        findings = health_module.check_hook_registration(healthy_repo)
        assert findings == []

    def test_missing_settings_detected(self, health_module: ModuleType, tmp_path: Path) -> None:
        findings = health_module.check_hook_registration(tmp_path)
        assert len(findings) == 1
        assert "settings file not found" in findings[0][2]
