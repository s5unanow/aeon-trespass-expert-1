"""Corpus-driven contract test for the parametrize red-before detector (S5U-819).

Mirrors ``test_check_visual_test_overrides_corpus.py`` for the
``scripts/check_parametrize_red_before.py`` detector (S5U-789 rollout).

Drives the REAL production entry point ``analyze_file(path, head_source,
added_lines) -> (matches, skips)`` — the same function ``main`` calls — over
every case in ``apps/pipeline/tests/safety_gate_corpus/parametrize_red_before.toml``.
Each snippet is fed as the head source with EVERY non-blank line treated as an
added diff line (the whole snippet is "the diff"):

* ``block``          → ``analyze_file`` must return >=1 ``Match`` and NO ``Skip``
  (a parse Skip on a block/allow case is a corpus typo and must not masquerade as
  a pass).
* ``allow``          → ``analyze_file`` must return 0 ``Match`` and 0 ``Skip``.
* ``known_residual`` → ``analyze_file`` returns 0 ``Match`` today (the detector
  stays silent); a Skip is permitted because the residual is the ``.py``-only
  detector ignoring a vitest ``.ts`` snippet. Pinned so a future TS-AST upgrade
  that closes the residual surfaces here and the case can flip to ``block``.

The corpus is the contract: a reviewer-found bypass is added as a ``block`` case
here, not patched in as a one-off regex. ``scripts/check_detector_corpus_coverage.py``
fails CI if ``scripts/check_parametrize_red_before.py`` changes without a change
to the corpus file.

Red-before confirmation: N/A — no production code change in this PR. The detector
``check_parametrize_red_before.py`` is unchanged; these cases pin its EXISTING
behavior as the named contract. The ``block`` cases are nonetheless real failure
inputs: the ``S5U-650-multiline-row`` / ``S5U-650-given-multiline-row`` snippets
carry no parametrize/``@given`` token on their added rows, so a regression of the
detector to a line-grep would make ``analyze_file`` return 0 matches and this test
go red — verified by ``test_corpus_pins_s5u650_regressions`` and by running the
detector against the snippets at this branch's base (matches=6 each). Reviewer
asked to cross-check the diff (no ``scripts/check_parametrize_red_before.py`` edit).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ._safety_gate_corpus import CorpusCase, load_corpus

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "check_parametrize_red_before.py"

_CASES = load_corpus("parametrize_red_before")


@pytest.fixture()
def detector(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Fresh import of check_parametrize_red_before.py per test."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_parametrize_red_before", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_parametrize_red_before"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("check_parametrize_red_before", None)


def _added_lines(snippet: str) -> list[int]:
    """Every non-blank 1-based line number — "the whole snippet is the diff"."""
    return [i + 1 for i, line in enumerate(snippet.splitlines()) if line.strip()]


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_parametrize_red_before_corpus_case(detector: ModuleType, case: CorpusCase) -> None:
    matches, skips = detector.analyze_file("snippet.py", case.snippet, _added_lines(case.snippet))
    detail = f"[{case.id}] {case.note or ''}".strip()
    rendered_skips = [s.reason for s in skips]

    if case.expect == "block":
        assert len(matches) >= 1, f"expected >=1 match but got none: {detail}"
        assert skips == [], f"block case must parse cleanly, got skips {rendered_skips}: {detail}"
    elif case.expect == "allow":
        assert matches == [], (
            f"expected 0 matches (allow) but got {[(m.line, m.context) for m in matches]}: {detail}"
        )
        assert skips == [], f"allow case must parse cleanly, got skips {rendered_skips}: {detail}"
    else:  # known_residual
        # The detector must stay SILENT on a residual. A parse Skip is permitted
        # (the residual is the .py-only detector ignoring a vitest .ts snippet).
        assert matches == [], (
            f"known_residual is no longer silent — got matches "
            f"{[(m.line, m.context) for m in matches]}. If the detector now covers "
            f"this case, flip it to `block`: {detail}"
        )


def test_corpus_pins_s5u650_regressions() -> None:
    """The S5U-650 multiline-row regressions must persist as `block` cases.

    ``load_corpus`` already fails closed on an empty case list; this pins the
    specific regression coverage so a future refactor cannot silently drop the
    named S5U-650 bypass class.
    """
    by_id = {c.id: c for c in _CASES}
    required_block = {"S5U-650-multiline-row", "S5U-650-given-multiline-row"}
    missing = required_block - by_id.keys()
    assert not missing, f"corpus dropped S5U-650 regression case(s): {sorted(missing)}"
    for case_id in required_block:
        assert by_id[case_id].expect == "block", f"{case_id} must be a `block` case"


def test_corpus_covers_every_expect_class() -> None:
    """A `block`, `allow`, and `known_residual` case must each be present.

    Guards against a corpus that silently degenerates into all-block (which would
    let a residual or false-positive guard go untracked).
    """
    expects = {c.expect for c in _CASES}
    assert {"block", "allow", "known_residual"} <= expects, f"missing expect class: {expects}"
