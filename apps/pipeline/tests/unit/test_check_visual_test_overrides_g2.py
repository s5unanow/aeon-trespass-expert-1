"""G2 content-derived match-set + adversarial inputs for `scripts/check_visual_test_overrides.py`.

Per `.claude/rules/guards.md` Rule G2, the blocked set is content-derived:
"every line whose body contains `maxDiffPixelRatio:` in any spec file under the
scan dir." Tests below exercise rename / wrapper / alias adversarial inputs:

- marker grammar variants (wrong spelling, wrong token, missing prefix)
- adjacency rules (immediate, blank-separated, two-lines-back)
- multi-line `toHaveScreenshot(...)` calls
- nested directory walking
- non-spec files ignored (keeps `playwright.config.ts` out of scope)
- token hidden in string literal (FP-tolerated; documented)
- CLI integration (clean / dirty / default-scan-dir)

`overrides_mod` fixture is auto-discovered from `tests/unit/conftest.py`.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from ._check_visual_test_overrides_helpers import write_spec


class TestG2AdversarialInputs:
    def test_marker_two_lines_back_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """Marker is not adjacent — there's an unrelated `await` line between."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "two_lines.spec.ts",
            "test('x', async () => {\n"
            "  // visual-gate-override: allow reason=intentional drift\n"
            "  await page.waitForLoad();\n"
            "  await expect(page).toHaveScreenshot('foo.png', {\n"
            "    maxDiffPixelRatio: 0.5,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_marker_blank_line_separated_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Blank lines between marker and override are walked over (allowed)."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "blank_sep.spec.ts",
            "test('x', async () => {\n"
            "  await expect(page).toHaveScreenshot('foo.png', {\n"
            "    // visual-gate-override: allow reason=intentional drift in PR #999\n"
            "\n"
            "    maxDiffPixelRatio: 0.5,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_marker_directly_above_override_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Canonical multi-line `toHaveScreenshot` shape with marker on the line above."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "multiline.spec.ts",
            "test('x', async () => {\n"
            "  await expect(page).toHaveScreenshot('foo.png', {\n"
            "    // visual-gate-override: allow reason=ascii-art drift\n"
            "    maxDiffPixelRatio: 0.05,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_wrong_spelling_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """`// visual-gate-override` (no `: allow reason=...`) is not a valid marker."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "wrong_spell.spec.ts",
            "test('x', async () => {\n"
            "  await expect(page).toHaveScreenshot('foo.png', {\n"
            "    // visual-gate-override\n"
            "    maxDiffPixelRatio: 0.5,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1

    def test_wrong_token_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """`// visual-gate: allow reason=...` (missing `-override`) is not a valid marker."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "wrong_token.spec.ts",
            "test('x', async () => {\n"
            "  await expect(page).toHaveScreenshot('foo.png', {\n"
            "    // visual-gate: allow reason=foo\n"
            "    maxDiffPixelRatio: 0.5,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1

    def test_inline_marker_on_same_line_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Marker on the same line as the override is also accepted."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "inline.spec.ts",
            "test('x', async () => {\n"
            "  await expect(page).toHaveScreenshot('foo.png', {\n"
            "    maxDiffPixelRatio: 0.5, // visual-gate-override: allow reason=intentional drift\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_token_in_string_literal_still_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Token hidden inside a string literal is still flagged (FP-tolerated by design)."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "stringlit.spec.ts",
            "test('x', () => {\n  const tip = 'maxDiffPixelRatio: never override';\n});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_multiple_specs_one_dirty_one_clean(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Content-derived: dirty file is found regardless of name; clean file passes."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "innocent_name.spec.ts",
            "await expect(page).toHaveScreenshot('foo.png', {\n  maxDiffPixelRatio: 0.99,\n});\n",
        )
        write_spec(
            scan_dir,
            "extraction-regression.spec.ts",
            "await expect(page).toHaveScreenshot('foo.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1
        assert "innocent_name.spec.ts" in violations[0].path

    def test_nested_directory_scanned(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """`rglob('*.spec.ts')` walks nested subdirectories — content-derived."""
        scan_dir = tmp_path / "e2e"
        nested = scan_dir / "deep" / "nested"
        write_spec(
            nested,
            "buried.spec.ts",
            "await expect(page).toHaveScreenshot('foo.png', { maxDiffPixelRatio: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1
        assert "buried.spec.ts" in violations[0].path

    def test_non_spec_file_ignored(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """Files not matching `*.spec.ts` ignored; keeps `playwright.config.ts` out of scope."""
        scan_dir = tmp_path / "e2e"
        scan_dir.mkdir(parents=True)
        # Non-spec file with the override token; must NOT be flagged.
        (scan_dir / "playwright.config.ts").write_text(
            "export default { expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.005 } } };\n"
        )
        # And one legitimate spec to keep the file list non-empty.
        write_spec(
            scan_dir,
            "ok.spec.ts",
            "await expect(page).toHaveScreenshot('foo.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


class TestMainCLI:
    def test_main_clean_returns_zero(
        self,
        overrides_mod: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "ok.spec.ts",
            "await expect(page).toHaveScreenshot('foo.png');\n",
        )
        rc = overrides_mod.main([str(scan_dir), "--repo-root", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "clean" in captured.out

    def test_main_dirty_returns_one(
        self,
        overrides_mod: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "bad.spec.ts",
            "await expect(page).toHaveScreenshot('foo.png', { maxDiffPixelRatio: 0.5 });\n",
        )
        rc = overrides_mod.main([str(scan_dir), "--repo-root", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "override-without-justification" in captured.err

    def test_main_default_scan_dir_uses_repo_root(
        self,
        overrides_mod: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Omitted `scan_dir` arg defaults to `<repo_root>/apps/web/tests/e2e`."""
        scan_dir = tmp_path / "apps" / "web" / "tests" / "e2e"
        write_spec(
            scan_dir,
            "default.spec.ts",
            "await expect(page).toHaveScreenshot('foo.png');\n",
        )
        rc = overrides_mod.main(["--repo-root", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "clean" in captured.out
