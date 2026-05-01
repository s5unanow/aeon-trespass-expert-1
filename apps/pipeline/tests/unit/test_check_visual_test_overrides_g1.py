"""G1 fail-closed defaults for `scripts/check_visual_test_overrides.py` (S5U-657, S5U-757).

Per `.claude/rules/guards.md` Rule G1, every degenerate-input case MUST exit
non-zero with a clear message — except the documented one deviation: an empty
spec-file list (no file matching the Playwright `testMatch` family) returns 0
with a stdout warning (see plan §4a).

`overrides_mod` fixture is auto-discovered from `tests/unit/conftest.py`.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from ._check_visual_test_overrides_helpers import write_spec


class TestG1FailClosed:
    def test_missing_scan_dir_raises(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="does not exist"):
            overrides_mod.scan(tmp_path / "missing", tmp_path)

    def test_scan_dir_is_file_raises(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_text("oops")
        with pytest.raises(RuntimeError, match="is not a directory"):
            overrides_mod.scan(not_a_dir, tmp_path)

    def test_unreadable_spec_file_raises(
        self,
        overrides_mod: ModuleType,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "ok.spec.ts",
            "test('x', async () => { await expect(page).toHaveScreenshot('a.png'); });\n",
        )
        original_read = Path.read_text

        def raising_read_text(self: Path, *args: object, **kwargs: object) -> str:
            if self.name == "ok.spec.ts":
                raise OSError("simulated permission denied")
            return original_read(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", raising_read_text)
        with pytest.raises(RuntimeError, match="cannot read"):
            overrides_mod.scan(scan_dir, tmp_path)

    def test_empty_spec_dir_returns_zero_with_warning(
        self,
        overrides_mod: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Empty spec-file list — documented G1 deviation: exit 0 with warning."""
        scan_dir = tmp_path / "e2e"
        scan_dir.mkdir(parents=True)
        rc = overrides_mod.main([str(scan_dir), "--repo-root", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "no spec files" in captured.out
        # Message should advertise the broadened Playwright `testMatch` family
        # (S5U-757) so anyone seeing the message in CI can understand the
        # extension set the scanner now covers.
        assert "spec,test" in captured.out

    def test_main_missing_scan_dir_exits_nonzero(
        self,
        overrides_mod: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = overrides_mod.main([str(tmp_path / "missing"), "--repo-root", str(tmp_path)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "does not exist" in captured.err

    def test_main_missing_repo_root_exits_nonzero(
        self,
        overrides_mod: ModuleType,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bogus_root = tmp_path / "no-such-root"
        rc = overrides_mod.main([str(tmp_path), "--repo-root", str(bogus_root)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "repo root" in captured.err
        assert "does not exist" in captured.err
