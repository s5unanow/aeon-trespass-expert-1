"""Corpus-driven contract test for the instruction-drift detector family
(S5U-820, child of S5U-789).

Drives the REAL production entry points of the six fail-closed instruction-drift
rules over every case in
``apps/pipeline/tests/safety_gate_corpus/instruction_drift.toml``, plus the
boundary-shape deserialization arm read live from ``.claude/prompts/review.md``
(S5U-756). Each case names a ``probe`` discriminator selecting which detector to
drive:

* ``claim_count``       → ``_instruction_drift_rule_a.py::scan_claim_drift``.
* ``retired_term``      → ``_instruction_drift_rule_b.py::scan_retired_terms``.
* ``safety_gate_scope`` → ``_instruction_drift_rule_c.py::scan_safety_gate_scope``
  (canonical read LIVE from CLAUDE.md via ``extract_canonical_safety_gate_list``).
* ``ci_gate_count``     → ``_instruction_drift_rule_e.py::scan_ci_gate_claims``.
* ``ci_inline_enum``    → ``_instruction_drift_rule_f.py::scan_ci_body_inline_enumeration``.
* ``tilde_fence``       → ``_instruction_drift_rule_g.py::scan_claude_md_tilde_fences``.
* ``tomli_arm``         → the live ``tomli\\.loads?\\(`` arm read from
  ``.claude/prompts/review.md``, grepped against the snippet (content-derived,
  like the boundary-shape harness reads the real shell ERE).

``expect`` semantics:

* ``block``          → the detector MUST catch the drift (>=1 message / regex match).
* ``allow``          → the detector MUST NOT flag legitimate / exempt input (0 msgs).
* ``known_residual`` → the detector does NOT catch it today (0 msgs). Pinned so a
  future fix that closes the residual surfaces here and the case can flip to ``block``.

The corpus is the contract (S5U-789): a reviewer-found bypass is added as a
``block`` case here, not patched in as a one-off regex.
``scripts/check_detector_corpus_coverage.py`` fails CI if any detector_source
changes without a change to the corpus file.

Red-before confirmation: see ``tmp/plan-s5u-820.md`` §8 — each ``block`` case was
proved to go RED under a scratch-worktree mutation reverting (or gutting) the
relevant detector to its pre-fix behavior. The ``known_residual`` (Rule E gap
detection) was proved to yield no message today, and declaring it ``block`` fails.
No detector script was edited by this PR.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ._safety_gate_corpus import CorpusCase, load_corpus

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
REVIEW_MD = REPO / ".claude" / "prompts" / "review.md"

_CASES = load_corpus("instruction_drift")

# Authoritative check count fed to Rule A's scan_claim_drift. Any int that
# differs from the cases' claimed sub-range Ns (21) so a stale claim drifts.
_AUTHORITATIVE_COUNT = 25


def _load_script_module(name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import a ``scripts/<name>.py`` module by file path (fresh per test)."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Rule E imports from rule_a's sibling? No — Rule F imports `_ci_section_body`
# and `walk_with_fence_state` from rule_e, and Rule G imports
# `walk_with_fence_state` from rule_e. The fixtures below load rule_e first so
# those imports resolve against the freshly-loaded module on sys.modules.
_RULE_MODULES = ("a", "b", "c", "e", "f", "g")


@pytest.fixture()
def rules(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, ModuleType]]:
    """Fresh import of every instruction-drift rule module per test.

    Loads rule_e before f/g so their ``from _instruction_drift_rule_e import …``
    statements bind to the freshly-loaded module.
    """
    loaded: dict[str, ModuleType] = {}
    # rule_e first (f and g import from it), then the rest.
    for suffix in ("a", "b", "c", "e", "f", "g"):
        name = f"_instruction_drift_rule_{suffix}"
        loaded[suffix] = _load_script_module(name, monkeypatch)
    yield loaded
    for suffix in _RULE_MODULES:
        sys.modules.pop(f"_instruction_drift_rule_{suffix}", None)


def _claim_count_caught(rule_a: ModuleType, snippet: str) -> bool:
    msgs: list[str] = []
    for line in snippet.splitlines() or [snippet]:
        msgs.extend(rule_a.scan_claim_drift(Path("DOC.md"), line, _AUTHORITATIVE_COUNT))
    return len(msgs) >= 1


def _retired_term_caught(rule_b: ModuleType, snippet: str) -> bool:
    return len(rule_b.scan_retired_terms("README.md", snippet)) >= 1


def _safety_gate_caught(rule_c: ModuleType, snippet: str) -> bool:
    canonical = rule_c.extract_canonical_safety_gate_list(REPO)
    msgs = rule_c.scan_safety_gate_scope(".claude/skills/x/SKILL.md", snippet, canonical)
    return len(msgs) >= 1


def _ci_gate_count_caught(rule_e: ModuleType, snippet: str) -> bool:
    return len(rule_e.scan_ci_gate_claims(snippet)) >= 1


def _ci_inline_enum_caught(rule_f: ModuleType, snippet: str) -> bool:
    return len(rule_f.scan_ci_body_inline_enumeration(snippet)) >= 1


def _tilde_fence_caught(rule_g: ModuleType, snippet: str) -> bool:
    return len(rule_g.scan_claude_md_tilde_fences(snippet)) >= 1


def _tomli_arm_pattern() -> str:
    """Read the live ``tomli\\.loads?\\(`` arm from .claude/prompts/review.md.

    Content-derived (mirrors the boundary-shape harness reading the real shell
    ERE): a regression that reverts the arm to ``tomli\\.loads\\(`` makes the
    file-form snippet stop matching and the corpus case goes red.
    """
    text = REVIEW_MD.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "tomli\\.load" in line:
            # The whole deserialization regex is on this line; extract just the
            # tomli arm so a sibling arm's drift cannot mask a tomli regression.
            for arm in line.split("|"):
                arm = arm.strip().strip("'")
                if arm.startswith("tomli\\.load"):
                    return arm
    raise AssertionError(".claude/prompts/review.md has no `tomli\\.load` regex arm")


def _tomli_arm_caught(snippet: str) -> bool:
    """True if the live review.md tomli arm matches the snippet via grep -Eq."""
    proc = subprocess.run(
        ["grep", "-Eq", "--", _tomli_arm_pattern()],
        input=snippet,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _run_probe(case: CorpusCase, rules: dict[str, ModuleType]) -> bool:
    """Drive the case's probe and return whether the detector caught it."""
    probe = case.probe
    if probe == "claim_count":
        return _claim_count_caught(rules["a"], case.snippet)
    if probe == "retired_term":
        return _retired_term_caught(rules["b"], case.snippet)
    if probe == "safety_gate_scope":
        return _safety_gate_caught(rules["c"], case.snippet)
    if probe == "ci_gate_count":
        return _ci_gate_count_caught(rules["e"], case.snippet)
    if probe == "ci_inline_enum":
        return _ci_inline_enum_caught(rules["f"], case.snippet)
    if probe == "tilde_fence":
        return _tilde_fence_caught(rules["g"], case.snippet)
    if probe == "tomli_arm":
        return _tomli_arm_caught(case.snippet)
    raise AssertionError(  # pragma: no cover - loader rejects unknown probes (G1)
        f"case {case.id} has no/unknown probe {case.probe!r}"
    )


def _assert_by_expect(expect: str, caught: bool, detail: str) -> None:
    """Common block/allow/known_residual assertion over a boolean ``caught``."""
    if expect == "block":
        assert caught, f"expected the detector to flag the snippet: {detail}"
    elif expect == "allow":
        assert not caught, f"expected the detector NOT to flag legitimate input: {detail}"
    else:  # known_residual
        assert not caught, (
            f"known_residual is no longer silent — the detector now catches "
            f"this; flip the case to `block`: {detail}"
        )


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_instruction_drift_corpus_case(case: CorpusCase, rules: dict[str, ModuleType]) -> None:
    detail = f"[{case.id}] {case.note or ''}".strip()
    caught = _run_probe(case, rules)
    _assert_by_expect(case.expect, caught, detail)


def test_rule_c_exact_canonical_allows(rules: dict[str, ModuleType]) -> None:
    """A skill re-citing the LIVE CLAUDE.md canonical verbatim must NOT drift.

    Built from the live source rather than a static snippet because the canonical
    enumeration evolves; pinning it statically would rot. Complements the
    corpus's C-block (trimmed) and C-allow (defers) cases with the
    byte-for-byte-match exemption.
    """
    rule_c = rules["c"]
    canonical = rule_c.extract_canonical_safety_gate_list(REPO)
    line = f"escalate per the safety-gate scope ({canonical}) enumeration"
    assert rule_c.scan_safety_gate_scope(".claude/skills/x/SKILL.md", line, canonical) == []


def test_corpus_pins_named_regressions() -> None:
    """The named S5U regression cases must persist (no silent drop).

    ``load_corpus`` already fails closed on an empty case list; this pins the
    specific named bypass classes so a future refactor cannot drop them.
    """
    by_id = {c.id: c for c in _CASES}
    required_block = {
        "S5U-820-A-block-stale-range",
        "S5U-820-A-block-stale-all",
        "S5U-820-B-block-bare-tesseract",
        "S5U-820-C-block-trimmed-list",
        "S5U-820-E-block-header-mismatch",
        "S5U-820-E-block-all-k-mismatch",
        "S5U-820-F-block-slash-compression",
        "S5U-820-F-block-and-compression",
        "S5U-820-G-block-active-tilde",
        "S5U-756-tomli-load-file-form",
        "S5U-756-tomli-loads-string-form",
    }
    missing = required_block - by_id.keys()
    assert not missing, f"corpus dropped regression case(s): {sorted(missing)}"
    for case_id in required_block:
        assert by_id[case_id].expect == "block", f"{case_id} must be a `block` case"
    # Rule E gap detection is the documented open residual.
    assert "S5U-820-E-known_residual-gap" in by_id
    assert by_id["S5U-820-E-known_residual-gap"].expect == "known_residual"


def test_corpus_covers_every_expect_class() -> None:
    """A `block`, `allow`, and `known_residual` case must each be present.

    Guards against a corpus that silently degenerates into all-block (which would
    let a residual or false-positive guard go untracked).
    """
    expects = {c.expect for c in _CASES}
    assert {"block", "allow", "known_residual"} <= expects, f"missing expect class: {expects}"


def test_every_case_declares_a_probe() -> None:
    """Every instruction-drift case must name a probe (multi-detector corpus).

    A case with ``probe=None`` would have no detector to drive and silently
    skip — the loader allows ``None`` for the single-detector corpora, so this
    corpus-specific invariant is asserted here.
    """
    missing = [c.id for c in _CASES if c.probe is None]
    assert not missing, f"instruction-drift cases missing a `probe`: {missing}"


def test_every_rule_family_has_a_block_case() -> None:
    """Each of the six fail-closed rules (A/B/C/E/F/G) plus the tomli arm must
    have at least one ``block`` case, so the migration covers the whole family.
    """
    block_probes = {c.probe for c in _CASES if c.expect == "block"}
    required = {
        "claim_count",
        "retired_term",
        "safety_gate_scope",
        "ci_gate_count",
        "ci_inline_enum",
        "tilde_fence",
        "tomli_arm",
    }
    missing = required - block_probes
    assert not missing, f"rule family missing a block case: {sorted(missing)}"
