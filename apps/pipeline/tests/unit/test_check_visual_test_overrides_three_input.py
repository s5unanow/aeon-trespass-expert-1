"""Three-input matrix tests for `scripts/check_visual_test_overrides.py` (S5U-657).

Bullets verbatim from Linear S5U-657 "Three-input test matrix":

* Happy: no overrides → pass
* Failure: override without justification comment → block with clear error
* Adversarial: override with empty/whitespace-only justification → block

Red-before confirmation: N/A — `scripts/check_visual_test_overrides.py` and these
tests are introduced together; no prior version of the script exists. Reviewer
cross-checks by deleting the production module: the `overrides_mod` fixture
would fail at module-load with FileNotFoundError, exercising the same import
path the tests rely on.

`overrides_mod` fixture is auto-discovered from `tests/unit/conftest.py`.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from ._check_visual_test_overrides_helpers import write_spec


class TestThreeInputMatrix:
    def test_happy_no_override_passes(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """Bullet: `Happy: no overrides → pass`."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "clean.spec.ts",
            """
            import { test, expect } from '@playwright/test';

            test('renders', async ({ page }) => {
              await expect(page).toHaveScreenshot('foo.png');
            });
            """,
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == []

    def test_override_without_marker_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Bullet: `Failure: override without justification comment → block with clear error`."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "bad.spec.ts",
            """
            test('drift', async ({ page }) => {
              await expect(page).toHaveScreenshot('foo.png', {
                maxDiffPixelRatio: 0.5,
              });
            });
            """,
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1
        assert "override-without-justification" in violations[0].reason

    def test_marker_with_empty_reason_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Bullet: `Adversarial: override with empty/whitespace-only justification → block`.

        Empty-reason variant.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "empty_reason.spec.ts",
            """
            test('drift', async ({ page }) => {
              await expect(page).toHaveScreenshot('foo.png', {
                // visual-gate-override: allow reason=
                maxDiffPixelRatio: 0.5,
              });
            });
            """,
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
        assert "override-without-justification" in violations[0].reason

    def test_marker_with_whitespace_only_reason_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Bullet: `Adversarial: override with empty/whitespace-only justification → block`.

        Whitespace-only-reason variant. Mirrors LOOSEN-THRESHOLD non-empty
        rule from S5U-591.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "ws_reason.spec.ts",
            "test('drift', async () => {\n"
            "  await expect(page).toHaveScreenshot('foo.png', {\n"
            "    // visual-gate-override: allow reason=    \n"
            "    maxDiffPixelRatio: 0.5,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
