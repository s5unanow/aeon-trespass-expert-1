"""S5U-757 — close 4 syntactic-variant bypasses in `scripts/check_visual_test_overrides.py`.

Reproduces the four override shapes the post-ship review of PR #364 surfaced
and verifies the hardened scanner blocks each one. Bullets verbatim from
Linear S5U-757 "Fix sketch":

* (F1) Broaden file-glob to Playwright's actual `testMatch`.
* (F2) Loosen the regex to handle bare-key, quoted-key, and property-shorthand.
* (F3) Computed-key form via the declaration-site ban.
* (F4) Add the four reproductions to the G2 test file.

Red-before confirmation: ran locally at `327fdea7d0e755fb004fc03cae4cb8fcd0406076`
(current `main` HEAD pre-fix). The four CLI reproductions in the Linear issue
all exited 0 ("clean (1 spec file(s) scanned ...)" or "no `*.spec.ts` files
found ..."). Each new test below was authored to assert the post-fix verdict;
each one fails on `327fdea` because the underlying scanner has not been
extended yet — quoted-key / shorthand / computed-key inputs return zero
violations from `scan()`, and `.spec.tsx` / `.test.ts` / `.spec.jsx` files
are not enumerated by `_iter_spec_files` at all (which means they cannot
even raise a violation). The plan's §4d enumerates the per-condition
red-before assertion shape.

`overrides_mod` fixture is auto-discovered from `tests/unit/conftest.py`.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from ._check_visual_test_overrides_helpers import write_spec

# ---------------------------------------------------------------------------
# Bypass #1 — ES6 property shorthand `{ maxDiffPixelRatio }`
# ---------------------------------------------------------------------------


class TestPropertyShorthand:
    def test_inline_shorthand_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """`{ maxDiffPixelRatio }` adjacent to `{` and `}` on the same line."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "shorthand_inline.spec.ts",
            "test('v', async () => {\n"
            "  const maxDiffPixelRatio = 0.5;\n"
            "  await expect(page).toHaveScreenshot('a.png', { maxDiffPixelRatio });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        # The shorthand line on line 3 fires the inline-shorthand regex.
        # The `const maxDiffPixelRatio = 0.5;` line on line 2 carries `=`
        # immediately after the token, so the shorthand regex's
        # negative-followed-by clause `(?![:=\w])` excludes it.
        assert len(violations) == 1, [v.format() for v in violations]
        assert "shorthand_inline.spec.ts" in violations[0].path
        assert violations[0].line == 3

    def test_inline_shorthand_with_marker_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """Marker on the immediately preceding line allows the shorthand override."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "shorthand_marker.spec.ts",
            "test('v', async () => {\n"
            "  const maxDiffPixelRatio = 0.5;\n"
            "  // visual-gate-override: allow reason=intentional drift PR #999\n"
            "  await expect(page).toHaveScreenshot('a.png', { maxDiffPixelRatio });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_multiline_shorthand_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """Multi-line shorthand: token alone on its own line bracketed by `,`/`}`."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "shorthand_multiline.spec.ts",
            "const maxDiffPixelRatio = 0.5;\n"
            "await expect(page).toHaveScreenshot('a.png', {\n"
            "  maxDiffPixelRatio,\n"
            "  fullPage: true,\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        # Line 3 has the token alone bracketed by `,` — the multiline
        # shorthand regex fires.
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 3

    def test_local_binding_alone_does_not_match(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """`const maxDiffPixelRatio = 0.5` on its own — no use site — must NOT flag.

        The binding line has `=` immediately after the token, so the shorthand
        regex's negative-followed-by clause `(?![:=\\w])` excludes it. The
        bare-or-quoted-colon regex requires a colon; absent. The
        computed-key-declaration regex requires the RHS to be a quoted-string
        equal to `'maxDiffPixelRatio'`; the RHS here is `0.5`, not a string,
        so it does not match. Net: clean.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "local_binding.spec.ts",
            "const maxDiffPixelRatio = 0.5;\nawait expect(page).toHaveScreenshot('a.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# ---------------------------------------------------------------------------
# Bypass #2 — Quoted property name `{ 'maxDiffPixelRatio': 0.5 }`
# ---------------------------------------------------------------------------


class TestQuotedKey:
    def test_single_quoted_key_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "quoted_single.spec.ts",
            "await expect(page).toHaveScreenshot('a.png', { 'maxDiffPixelRatio': 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_double_quoted_key_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "quoted_double.spec.ts",
            'await expect(page).toHaveScreenshot("a.png", { "maxDiffPixelRatio": 0.5 });\n',
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_quoted_key_with_marker_passes(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "quoted_marker.spec.ts",
            "// visual-gate-override: allow reason=intentional drift\n"
            "await expect(page).toHaveScreenshot('a.png', { 'maxDiffPixelRatio': 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# ---------------------------------------------------------------------------
# Bypass #3 — Computed key `{ [k]: 0.5 }` with `const k = 'maxDiffPixelRatio'`
# ---------------------------------------------------------------------------


class TestComputedKey:
    def test_const_string_binding_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """`const k = 'maxDiffPixelRatio'` is the static anchor for the computed-key form."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "computed_const.spec.ts",
            "const k = 'maxDiffPixelRatio';\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]
        assert violations[0].line == 1

    def test_let_string_binding_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        """`let` and `var` are also caught."""
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "computed_let.spec.ts",
            'let k = "maxDiffPixelRatio";\n'
            'await expect(page).toHaveScreenshot("a.png", { [k]: 0.5 });\n',
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_var_string_binding_blocks(self, overrides_mod: ModuleType, tmp_path: Path) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "computed_var.spec.ts",
            "var k = 'maxDiffPixelRatio';\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, [v.format() for v in violations]

    def test_computed_key_with_marker_passes(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "computed_marker.spec.ts",
            "// visual-gate-override: allow reason=intentional drift\n"
            "const k = 'maxDiffPixelRatio';\n"
            "await expect(page).toHaveScreenshot('a.png', { [k]: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_prose_string_with_token_does_not_false_positive(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """A const bound to a sentence containing the token — but not equal — must NOT flag.

        The computed-key declaration regex anchors on a closing quote
        IMMEDIATELY after the token. Sentence prose has additional characters
        between the token and the closing quote, so the regex does not match.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "prose_string.spec.ts",
            "const note = 'maxDiffPixelRatio is the central threshold name';\n"
            "await expect(page).toHaveScreenshot('a.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        # The token DOES appear inside a string literal, which IS FP-tolerated
        # by the existing scanner — but the only regex that could fire on this
        # line is the bare-or-quoted regex, which requires the token to be
        # followed by `:`. Here the token is followed by ` is the central…`,
        # not `:`, so no regex matches and the line is clean.
        assert violations == [], [v.format() for v in violations]


# ---------------------------------------------------------------------------
# Bypass #4 — File extensions other than `.spec.ts`
# ---------------------------------------------------------------------------


class TestBroadenedFileGlob:
    @pytest.mark.parametrize(
        "filename",
        [
            "v.spec.tsx",
            "v.spec.js",
            "v.spec.jsx",
            "v.spec.mjs",
            "v.spec.cjs",
            "v.test.ts",
            "v.test.tsx",
            "v.test.js",
            "v.test.jsx",
            "v.test.mjs",
            "v.test.cjs",
        ],
    )
    def test_extended_extensions_scanned(
        self, overrides_mod: ModuleType, tmp_path: Path, filename: str
    ) -> None:
        """Each Playwright-default `testMatch` extension must be enumerated.

        Red-before: every row in this parametrize block exercises a code
        branch (an extension) that pre-fix `_iter_spec_files` did NOT walk
        (it called `rglob('*.spec.ts')` only). Each row therefore exercises
        a distinct new branch in the broadened glob loop.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            filename,
            "await expect(page).toHaveScreenshot('a.png', { maxDiffPixelRatio: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert len(violations) == 1, (filename, [v.format() for v in violations])
        assert filename in violations[0].path

    def test_config_extension_still_out_of_scope(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """`playwright.config.ts` must NOT be picked up by the broadened glob.

        The new glob is `*.{spec,test}.{ts,tsx,js,jsx,mjs,cjs}` — `.config.ts`
        does not match any of those extensions, so the file is skipped.
        """
        scan_dir = tmp_path / "e2e"
        scan_dir.mkdir(parents=True)
        (scan_dir / "playwright.config.ts").write_text(
            "export default { expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.5 } } };\n"
        )
        write_spec(
            scan_dir,
            "ok.spec.ts",
            "await expect(page).toHaveScreenshot('a.png');\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_pathological_suffix_not_matched(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        """`foo.spec.ts.bak` and `foo.spec.tsxx` must NOT match the glob.

        `Path('foo.spec.ts.bak').match('*.spec.ts')` is False (the entire
        filename must end with the suffix); same for `.tsxx`. This prevents
        accidental scans of backup files or one-off typoed extensions.
        """
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "foo.spec.ts.bak",
            "await expect(page).toHaveScreenshot('a.png', { maxDiffPixelRatio: 0.5 });\n",
        )
        write_spec(
            scan_dir,
            "foo.spec.tsxx",
            "await expect(page).toHaveScreenshot('a.png', { maxDiffPixelRatio: 0.5 });\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]


# ---------------------------------------------------------------------------
# Cross-cutting: marker preserves carve-out across all syntactic variants
# ---------------------------------------------------------------------------


class TestMarkerCarveoutAcrossVariants:
    """Smoke-tests that the existing marker grammar still works across the new forms."""

    def test_marker_directly_above_quoted_key(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "quoted_above.spec.tsx",
            "test('v', async () => {\n"
            "  await expect(page).toHaveScreenshot('a.png', {\n"
            "    // visual-gate-override: allow reason=ascii-art drift\n"
            "    'maxDiffPixelRatio': 0.05,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]

    def test_marker_directly_above_multiline_shorthand(
        self, overrides_mod: ModuleType, tmp_path: Path
    ) -> None:
        scan_dir = tmp_path / "e2e"
        write_spec(
            scan_dir,
            "shorthand_above.test.ts",
            "const maxDiffPixelRatio = 0.5;\n"
            "test('v', async () => {\n"
            "  await expect(page).toHaveScreenshot('a.png', {\n"
            "    // visual-gate-override: allow reason=intentional drift\n"
            "    maxDiffPixelRatio,\n"
            "  });\n"
            "});\n",
        )
        violations = overrides_mod.scan(scan_dir, tmp_path)
        assert violations == [], [v.format() for v in violations]
