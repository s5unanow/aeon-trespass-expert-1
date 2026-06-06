"""Corpus-driven contract test for the parametrize red-before detector (S5U-819).

Mirrors ``test_check_visual_test_overrides_corpus.py`` for the
``scripts/check_parametrize_red_before.py`` detector (S5U-789 rollout).

Drives the REAL production entry point ``analyze_file(path, head_source,
added_lines) -> (matches, skips)`` — the same function ``main`` calls — over
every case in ``apps/pipeline/tests/safety_gate_corpus/parametrize_red_before.toml``.
Each snippet is fed as the head source. By default EVERY non-blank line is treated
as an added diff line (the whole snippet is "the diff"). A case MAY instead declare
an explicit ``added_lines = [...]`` (see ``CorpusCase.added_lines``) to model a REAL
diff in which only those rows are ``+``-added and the decorator/import lines are
UNCHANGED context — this is what makes the enclosing-context AST walk load-bearing
and is required for the S5U-650 multiline-bare-row cases (S5U-921). Per ``expect``:

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

Red-before confirmation (S5U-921): the harness was false-green before this change.
``_added_lines()`` fed the WHOLE snippet — including the token-bearing decorator/
import line — as "the diff", so a detector regressed to the pre-S5U-650 line-grep
(flag only added lines whose own text carries a token) still matched the decorator
line and every ``block`` case stayed green. With this fix the S5U-650 cases declare
``added_lines`` pointing ONLY at their token-less bare-tuple/strategy rows, and the
harness additionally asserts the matched line IS that bare-row line. A line-grep
mutation (M2) of ``analyze_file`` now makes both S5U-650 cases return 0 matches and
this test goes red - verified by applying the M2 mutation to a scratch copy of the
detector (see ``tmp/plan-s5u-921.md`` M1-M4 matrix). No
``scripts/check_parametrize_red_before.py`` edit; reviewer asked to cross-check.
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


def _diff_lines(case: CorpusCase) -> list[int]:
    """The lines fed as "the diff": explicit ``added_lines`` or the whole snippet.

    An explicit ``added_lines`` models a real PR where only the genuinely-added
    rows are ``+`` and the decorator/import lines are unchanged context. This is
    what makes the enclosing-context AST walk load-bearing (S5U-921).
    """
    if case.added_lines is not None:
        return list(case.added_lines)
    return _added_lines(case.snippet)


# The token-less bare row whose detection requires the enclosing-context AST walk
# (S5U-650). A match attributable only to the decorator/import line — i.e. a
# line-grep regression — would NOT report these line numbers, so asserting the
# match lands on the bare row binds the AST walk (S5U-921 fix-sketch option 2).
_S5U650_BARE_ROW: dict[str, int] = {
    "S5U-650-multiline-row": 6,
    "S5U-650-given-multiline-row": 8,
}


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_parametrize_red_before_corpus_case(detector: ModuleType, case: CorpusCase) -> None:
    matches, skips = detector.analyze_file("snippet.py", case.snippet, _diff_lines(case))
    detail = f"[{case.id}] {case.note or ''}".strip()
    rendered_skips = [s.reason for s in skips]

    if case.expect == "block":
        assert len(matches) >= 1, f"expected >=1 match but got none: {detail}"
        assert skips == [], f"block case must parse cleanly, got skips {rendered_skips}: {detail}"
        if case.id in _S5U650_BARE_ROW:
            bare_row = _S5U650_BARE_ROW[case.id]
            matched_lines = sorted(m.line for m in matches)
            assert bare_row in matched_lines, (
                f"S5U-650 case must flag the token-less bare row (line {bare_row}) "
                f"by enclosing context, not just the decorator line; matched "
                f"{matched_lines}. A line-grep regression cannot satisfy this: {detail}"
            )
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


def test_s5u650_cases_feed_only_token_less_rows(detector: ModuleType) -> None:
    """The S5U-650 cases must declare ``added_lines`` excluding the token line.

    This is the S5U-921 fix invariant: if a future refactor drops ``added_lines``
    (reverting to whole-snippet), the token-bearing decorator/import line would be
    fed as added, a line-grep regression would match it, and the cases would
    false-pass again. Pin that (a) ``added_lines`` is set, (b) the declared rows
    carry no parametrize/given token in their own text, and (c) the AST detector
    still flags exactly the declared bare row. (a)+(b) make a line-grep go red;
    (c) confirms the legitimate detector stays green.
    """
    _TOKENS = ("parametrize", "given", "params", "pytest_generate_tests")
    by_id = {c.id: c for c in _CASES}
    for case_id, bare_row in _S5U650_BARE_ROW.items():
        case = by_id[case_id]
        assert case.added_lines is not None, (
            f"{case_id} must declare `added_lines` (S5U-921); whole-snippet "
            "feeding re-opens the line-grep false-green"
        )
        snippet_lines = case.snippet.splitlines()
        for line_no in case.added_lines:
            own_text = snippet_lines[line_no - 1]
            assert not any(tok in own_text for tok in _TOKENS), (
                f"{case_id} `added_lines` row {line_no} ({own_text!r}) carries a "
                "parametrize/given token in its own text — a line-grep would match "
                "it and the case would not bind the AST walk"
            )
        matches, _ = detector.analyze_file("snippet.py", case.snippet, list(case.added_lines))
        assert sorted(m.line for m in matches) == [bare_row], (
            f"{case_id}: AST detector must flag exactly the bare row {bare_row}; "
            f"got {sorted(m.line for m in matches)}"
        )


def test_corpus_covers_every_expect_class() -> None:
    """A `block`, `allow`, and `known_residual` case must each be present.

    Guards against a corpus that silently degenerates into all-block (which would
    let a residual or false-positive guard go untracked).
    """
    expects = {c.expect for c in _CASES}
    assert {"block", "allow", "known_residual"} <= expects, f"missing expect class: {expects}"
