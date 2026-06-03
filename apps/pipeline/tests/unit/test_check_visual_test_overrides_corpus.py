"""Corpus-driven contract test for the maxDiffPixelRatio detector (S5U-789).

Drives the REAL ``scan()`` entry point (production path, per the S5U-791
"production-path regression proof" concern) over every case in
``apps/pipeline/tests/safety_gate_corpus/maxdiffpixelratio.toml``:

* ``block``          → ``scan()`` must return >=1 violation.
* ``allow``          → ``scan()`` must return 0 violations.
* ``known_residual`` → ``scan()`` returns 0 today; pinned so a future detector
  upgrade that closes the residual surfaces here and the case can flip to
  ``block``.

The corpus is the contract: a reviewer-found bypass is added as a ``block``
case here, not patched in as a one-off regex. ``scripts/check_detector_corpus_coverage.py``
fails CI if ``scripts/check_visual_test_overrides.py`` changes without a change
to the corpus file.

Red-before confirmation: the ``S5U-760..764`` and ``S5U-759-multiline-array``
``block`` rows exercise the new token-anchored branch
(``OVERRIDE_STRING_LITERAL_RE``) added by S5U-789. At ``0a290f1`` (this
branch's base, pre-rework) ``scan()`` returned ``[]`` for each of these inputs
— verified by running ``scripts/check_visual_test_overrides.py`` against the
five repros at that SHA (exit 0, "clean (5 spec file(s) scanned)"). Post-rework
each returns >=1 violation, which is what these rows assert.

``overrides_mod`` fixture is auto-discovered from ``tests/unit/conftest.py``.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from ._check_visual_test_overrides_helpers import write_spec
from ._safety_gate_corpus import CorpusCase, load_corpus

_CASES = load_corpus("maxdiffpixelratio")


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_maxdiff_corpus_case(overrides_mod: ModuleType, tmp_path: Path, case: CorpusCase) -> None:
    scan_dir = tmp_path / "e2e"
    write_spec(scan_dir, "corpus_case.spec.ts", case.snippet)
    violations = overrides_mod.scan(scan_dir, tmp_path)
    rendered = [v.format() for v in violations]
    detail = f"[{case.id}] {case.note or ''}".strip()

    if case.expect == "block":
        assert len(violations) >= 1, f"expected >=1 violation but got none: {detail}"
    else:
        # allow OR known_residual: the detector must stay silent.
        assert violations == [], (
            f"expected 0 violations ({case.expect}) but got {rendered}: {detail}"
        )


def test_corpus_is_non_trivial() -> None:
    """Guard against a silently-empty corpus and ensure regression IDs persist.

    The named bypass regressions (S5U-760..764) must remain in the corpus so a
    future refactor cannot drop them. ``load_corpus`` already fails closed on an
    empty case list; this pins the specific regression coverage.
    """
    ids = {c.id for c in _CASES}
    required = {
        "S5U-760-map-set",
        "S5U-761-tagged-template",
        "S5U-762-reassignment",
        "S5U-763-function-default-param",
        "S5U-764-computed-property-assignment",
    }
    missing = required - ids
    assert not missing, f"corpus dropped regression case(s): {sorted(missing)}"
    assert any(c.expect == "known_residual" for c in _CASES)
    assert any(c.expect == "allow" for c in _CASES)
