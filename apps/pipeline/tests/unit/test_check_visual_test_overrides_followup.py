"""S5U-759 — close 5 more syntactic-variant bypasses in the visual-overrides scanner.

Five override shapes surfaced by the post-ship review of PR #366; A/B/C/E
must block, D pins the documented residual.

Bypasses (Linear S5U-759 "Fix sketch"):
* (A) Backtick template literal as computed-key declaration RHS.
* (B) Inline string-literal computed key (no intermediate variable).
* (C) Inline backtick computed key.
* (D) Template-literal concatenation — DOCUMENTED RESIDUAL (undecidable by
      static line-regex; test pins the limit).
* (E) Array-literal indexed lookup.

Red-before confirmation: commit `f9e451caadf0fdd7edc6373d29a9639757e1cae0`
(current `main` HEAD pre-fix). On that SHA, the A/B/C/E and combined-repro
tests fail with `AssertionError: assert 0 == 1` — `overrides_mod.scan(...)`
returns `[]` (empty violations list) for each of those inputs because the
post-S5U-757 regexes do not admit backtick delimiters, inline computed-key
shapes, or array-literal RHS declarations. The Bypass D and multi-line
array residual tests pin documented limits and pass pre- and post-fix.

`overrides_mod` fixture is auto-discovered from `tests/unit/conftest.py`.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from ._check_visual_test_overrides_helpers import write_spec


# Bypass A — backtick template literal as computed-key declaration RHS.
class TestBypassA:
    def test_backtick_template_literal_decl_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """`const k = ` + backtick-token + backtick + `;` should be flagged.

        Pre-fix: the computed-key declaration regex character class is
        `['"]`, which excludes the backtick. Scanner returns [].
        Post-fix: quote class is `[\\x60'"]`, includes backtick; flags line 1.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "backtick_decl.spec.ts",
            "const k = `maxDiffPixelRatio`;\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 1
        assert "backtick_decl.spec.ts" in violations[0].path

    def test_backtick_decl_let_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """`let` and `var` are also caught with backtick RHS."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "backtick_let.spec.ts",
            "let k = `maxDiffPixelRatio`;\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_backtick_decl_with_marker_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Marker on the immediately preceding line allows a backtick-bound override."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "backtick_marker.spec.ts",
            "// visual-gate-override: allow reason=intentional drift PR #999\n"
            "const k = `maxDiffPixelRatio`;\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# ---------------------------------------------------------------------------
# Bypass B — Inline string-literal computed key (no intermediate variable)
# ---------------------------------------------------------------------------


class TestBypassB:
    def test_inline_single_quoted_computed_key_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """`{ ['maxDiffPixelRatio']: 0.5 }` — closing-quote-then-`]:` shape."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "inline_single.spec.ts",
            "await expect(page).toHaveScreenshot('a.png', { ['maxDiffPixelRatio']: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 1

    def test_inline_double_quoted_computed_key_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Double-quoted variant of Bypass B."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "inline_double.spec.ts",
            'await expect(page).toHaveScreenshot("a.png", { ["maxDiffPixelRatio"]: 0.5 });\n',
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_inline_string_computed_key_with_marker_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Marker carve-out across a B-shape override."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "inline_marker.spec.ts",
            "// visual-gate-override: allow reason=intentional drift\n"
            "await expect(page).toHaveScreenshot('a.png', { ['maxDiffPixelRatio']: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# ---------------------------------------------------------------------------
# Bypass C — Inline backtick computed key
# ---------------------------------------------------------------------------


class TestBypassC:
    def test_inline_backtick_computed_key_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """`{ [` + backtick-token + backtick + `]: 0.5 }` — backtick variant of B."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "inline_backtick.spec.ts",
            "await expect(page).toHaveScreenshot('a.png', { [`maxDiffPixelRatio`]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 1

    def test_inline_backtick_with_marker_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "inline_backtick_marker.spec.ts",
            "// visual-gate-override: allow reason=intentional drift\n"
            "await expect(page).toHaveScreenshot('a.png', { [`maxDiffPixelRatio`]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# Bypass D — template-literal concatenation (DOCUMENTED RESIDUAL).


class TestBypassD:
    def test_template_concat_documented_residual(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Pin the documented limit (plan §4d, option c).

        Token is constructed at runtime from `'maxDiff' + 'PixelRatio'` and
        never appears as a contiguous string. Static line-regex CANNOT detect
        this without an AST-based analyzer. If a future PR adds AST-based
        detection, this test must be updated.

        N/A — no production code change in this PR will close this gap;
        scanner behavior is invariant pre- and post-fix.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "template_concat.spec.ts",
            "const prefix = 'maxDiff';\n"
            "const k = `${prefix}PixelRatio`;\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# Bypass E — array-literal indexed lookup.


class TestBypassE:
    def test_array_literal_binding_index_zero_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """`const keys = ['maxDiffPixelRatio'];` — array-literal RHS."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "array_literal.spec.ts",
            "const keys = ['maxDiffPixelRatio'];\n"
            "await expect(page).toHaveScreenshot('a.png', { [keys[0]]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 1

    def test_array_literal_binding_index_n_blocks(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Token at index >0 in array-literal RHS is also flagged.

        The use site `[keys[N]]: 0.5` is undecidable by line-regex regardless
        of N, so the scanner must anchor on the declaration site and flag any
        array literal containing the token in any position.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "array_literal_idx_n.spec.ts",
            "const keys = ['other', 'maxDiffPixelRatio', 'third'];\n"
            "await expect(page).toHaveScreenshot('a.png', { [keys[1]]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 1

    def test_array_literal_backtick_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """Array-literal RHS with backtick-quoted token."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "array_literal_backtick.spec.ts",
            "const keys = [`maxDiffPixelRatio`];\n"
            "await expect(page).toHaveScreenshot('a.png', { [keys[0]]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_array_literal_with_marker_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "array_literal_marker.spec.ts",
            "// visual-gate-override: allow reason=intentional drift\n"
            "const keys = ['maxDiffPixelRatio'];\n"
            "await expect(page).toHaveScreenshot('a.png', { [keys[0]]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_multiline_array_now_blocked_s5u789(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Multi-line array literal with token on its own line — NOW BLOCKED (S5U-789).

        This was a documented residual under the binding-shape regex set:
        the `OVERRIDE_ARRAY_LITERAL_DECL_RE` required `const keys = [` and the
        token on the *same* line. S5U-789 reworked the detector to anchor on
        the token-as-string-literal (`OVERRIDE_STRING_LITERAL_RE`), which
        matches `'maxDiffPixelRatio'` on its own line regardless of where the
        `[` opener sits — closing the residual.

        Red-before: at `0a290f1` (branch base, pre-S5U-789) `scan()` returned
        `[]` for this input (the old residual). Post-rework it returns one
        violation on line 2.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "array_multiline.spec.ts",
            "const keys = [\n"
            "  'maxDiffPixelRatio',\n"
            "];\n"
            "await expect(page).toHaveScreenshot('a.png', { [keys[0]]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        # Token appears contiguously on line 2 → P1 (OVERRIDE_STRING_LITERAL_RE).
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 2


# False-positive regression — new regexes must not break existing FP defenses.


class TestNoFalsePositiveRegression:
    def test_prose_string_with_token_still_clean(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Backtick-quoted prose with token (not a binding) must NOT flag.

        Closing-backtick anchor (immediately after the token) blocks this —
        prose has more characters after the token before the closing backtick.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "prose_backtick.spec.ts",
            "const note = `maxDiffPixelRatio is the central threshold name`;\n"
            "await expect(page).toHaveScreenshot('a.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_prose_single_quoted_with_token_still_clean(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Existing S5U-757 prose-string FP defense must continue to pass."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "prose_single.spec.ts",
            "const note = 'maxDiffPixelRatio is the central threshold name';\n"
            "await expect(page).toHaveScreenshot('a.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_array_with_unrelated_strings_not_flagged(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Array-literal regex must not FP on arrays without the token."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "array_unrelated.spec.ts",
            "const keys = ['foo', 'bar', 'baz'];\nawait expect(page).toHaveScreenshot('a.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# Combined-bypass repro from the Linear issue body.


class TestCombinedRepro:
    def test_all_five_bypasses_combined(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """Mirror the Linear issue's combined repro — all 5 spec files in one dir.

        Pre-fix: scanner returns [] (exit 0 in CLI form). Post-fix: scanner
        returns 4 violations (A, B, C, E) and accepts D as documented residual.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "b1_backtick.spec.ts",
            "const k = `maxDiffPixelRatio`;\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        write_spec(
            scan_dir,
            "b2_inline_string.spec.ts",
            "await expect(page).toHaveScreenshot('a.png', { ['maxDiffPixelRatio']: 0.5 });\n",
        )
        write_spec(
            scan_dir,
            "b3_inline_backtick.spec.ts",
            "await expect(page).toHaveScreenshot('a.png', { [`maxDiffPixelRatio`]: 0.5 });\n",
        )
        write_spec(
            scan_dir,
            "b4_template_concat.spec.ts",
            "const prefix = 'maxDiff';\n"
            "const k = `${prefix}PixelRatio`;\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        write_spec(
            scan_dir,
            "b5_array_lookup.spec.ts",
            "const keys = ['maxDiffPixelRatio'];\n"
            "await expect(page).toHaveScreenshot('a.png', { [keys[0]]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        # 4 of 5 must be flagged (A, B, C, E); D is the documented residual.
        flagged_files = {Path(v.path).name for v in violations}
        assert "b1_backtick.spec.ts" in flagged_files, [v.format() for v in violations]
        assert "b2_inline_string.spec.ts" in flagged_files, [v.format() for v in violations]
        assert "b3_inline_backtick.spec.ts" in flagged_files, [v.format() for v in violations]
        assert "b5_array_lookup.spec.ts" in flagged_files, [v.format() for v in violations]
        # Bypass D must NOT be flagged (documented residual).
        assert "b4_template_concat.spec.ts" not in flagged_files, [v.format() for v in violations]
