"""Tests for golden refresh guard and extraction scope detection scripts."""

from __future__ import annotations

import fnmatch
import json
import subprocess
import sys
from pathlib import Path

from atr_pipeline.config.loader import _find_repo_root

REPO_ROOT = _find_repo_root()
SCRIPTS = REPO_ROOT / "scripts"

# Inline the patterns to avoid importing the script module
EXTRACTION_PATTERNS: dict[str, list[str]] = {
    "schema": [
        "packages/schemas/python/atr_schemas/native_page_*",
        "packages/schemas/python/atr_schemas/layout_page_*",
        "packages/schemas/python/atr_schemas/page_ir_*",
        "packages/schemas/python/atr_schemas/asset_*",
        "packages/schemas/python/atr_schemas/symbol_*",
        "packages/schemas/python/atr_schemas/page_evidence_*",
        "packages/schemas/python/atr_schemas/resolved_page_*",
    ],
    "golden_fixtures": [
        "packages/fixtures/**/expected/*",
    ],
}


def _match_areas(files: list[str]) -> set[str]:
    """Match files against extraction patterns."""
    matched: set[str] = set()
    for area, patterns in EXTRACTION_PATTERNS.items():
        for f in files:
            for p in patterns:
                if fnmatch.fnmatch(f, p):
                    matched.add(area)
                    break
    return matched


class TestGoldenRefreshGuard:
    """Tests for scripts/check_golden_refresh.py core logic."""

    def _run_guard(
        self, base: str = "HEAD", head: str = "HEAD"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "check_golden_refresh.py"),
                "--base",
                base,
                "--head",
                head,
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )

    def test_no_golden_changes_passes(self) -> None:
        result = self._run_guard(base="HEAD", head="HEAD")
        assert result.returncode == 0
        assert "No golden fixture files changed" in result.stdout


class TestExtractionScope:
    """Tests for scripts/check_extraction_scope.py core logic."""

    def _run_scope(
        self, base: str = "HEAD", head: str = "HEAD", output_json: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            sys.executable,
            str(SCRIPTS / "check_extraction_scope.py"),
            "--base",
            base,
            "--head",
            head,
        ]
        if output_json:
            cmd.extend(["--output-json", str(output_json)])
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )

    def test_no_changes_returns_empty(self) -> None:
        result = self._run_scope(base="HEAD", head="HEAD")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["areas"] == []
        assert data["mandatory_checks"] == []
        assert data["golden_refresh_detected"] is False
        assert data["threshold_change_detected"] is False

    def test_output_json_written(self, tmp_path: Path) -> None:
        out = tmp_path / "scope.json"
        result = self._run_scope(base="HEAD", head="HEAD", output_json=out)
        assert result.returncode == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert "areas" in data


class TestExtractionScopePatterns:
    """Test the pattern matching logic directly."""

    def test_schema_file_detected(self) -> None:
        areas = _match_areas(["packages/schemas/python/atr_schemas/page_ir_v1.py"])
        assert "schema" in areas

    def test_golden_file_detected(self) -> None:
        areas = _match_areas(["packages/fixtures/sample_documents/x/expected/page.json"])
        assert "golden_fixtures" in areas

    def test_unrelated_file_not_detected(self) -> None:
        areas = _match_areas(["apps/web/src/App.tsx"])
        assert areas == set()
