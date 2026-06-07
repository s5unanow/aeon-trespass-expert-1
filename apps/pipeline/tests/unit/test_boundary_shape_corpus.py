"""Corpus-driven contract test for the boundary-shape / fenced-section probes
(S5U-821, child of S5U-789).

Drives the REAL production entry points of four safety-gate detectors over every
case in ``apps/pipeline/tests/safety_gate_corpus/boundary_shape.toml``. Each case
names a ``probe`` discriminator selecting which detector to drive:

* ``forbidden_flag``   → ``check_visual_gate_scope.py::_contains_forbidden_flag``
  AND the real ``pattern=`` line read from ``check_test_e2e_flags.sh`` (both the
  Python and shell surfaces of the S5U-655 terminator broadening).
* ``local_only_token`` → ``check_visual_gate_scope.py::_local_only_token_patterns``.
* ``segment_splitter`` → ``_instruction_drift_rule_a.py::scan_claim_drift`` (the
  S5U-676 per-segment claim scan).
* ``ci_section_fence`` → ``_instruction_drift_rule_e.py::_ci_section_body`` (the
  S5U-742/743 CommonMark fence-aware body slice; ``probe_target`` is the
  enumerated item the slice must reach for ``block`` / must NOT reach for
  ``known_residual``).

``expect`` semantics:

* ``block``          → the detector MUST catch the bypass (>=1 match / fires /
  the fence slice reaches ``probe_target``).
* ``allow``          → the detector MUST NOT flag legitimate input (0 matches),
  and for the fence probe the slice terminates at a real out-of-fence heading
  (``probe_target`` excluded, but the pre-heading content IS present).
* ``known_residual`` → the detector does NOT catch it today (0 matches / the
  fence slice does NOT reach ``probe_target``). Pinned so a future fix that
  closes the residual surfaces here and the case can flip to ``block``.

The corpus is the contract (S5U-789): a reviewer-found bypass is added as a
``block`` case here, not patched in as a one-off regex.
``scripts/check_detector_corpus_coverage.py`` fails CI if any detector_source
changes without a change to the corpus file.

Red-before confirmation: see ``tmp/plan-s5u-821.md`` §5 — each ``block`` case was
proved to go RED under a scratch-copy mutation reverting the relevant detector to
its pre-fix behavior (terminator class, whole-line exemption, length-blind fence
toggle). The ``known_residual`` (S5U-744 tilde fence) was proved to yield no
match today, and declaring it ``block`` fails. No detector script was edited.
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
SHELL_GUARD = SCRIPT_DIR / "check_test_e2e_flags.sh"

_CASES = load_corpus("boundary_shape")

_AUTHORITATIVE_COUNT = 25  # any int != the claimed sub-range Ns in the corpus


def _load_script_module(name: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import a ``scripts/<name>.py`` module by file path."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def visual_gate(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Fresh import of check_visual_gate_scope.py per test."""
    yield _load_script_module("check_visual_gate_scope", monkeypatch)
    sys.modules.pop("check_visual_gate_scope", None)


@pytest.fixture()
def rule_a(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Fresh import of _instruction_drift_rule_a.py per test."""
    yield _load_script_module("_instruction_drift_rule_a", monkeypatch)
    sys.modules.pop("_instruction_drift_rule_a", None)


@pytest.fixture()
def rule_e(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Fresh import of _instruction_drift_rule_e.py per test."""
    yield _load_script_module("_instruction_drift_rule_e", monkeypatch)
    sys.modules.pop("_instruction_drift_rule_e", None)


def _shell_pattern() -> str:
    """Read the real forbidden-flag ERE from check_test_e2e_flags.sh.

    Binds the contract to the actual shell source (content-derived, not a copied
    regex): a regression in the shell ``pattern=`` line makes the grep below
    stop matching the terminator inputs and the corpus case goes red.
    """
    text = SHELL_GUARD.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("pattern="):
            # Strip `pattern=` and the surrounding single quotes.
            raw = stripped[len("pattern=") :]
            return raw[1:-1] if raw.startswith("'") and raw.endswith("'") else raw
    raise AssertionError("check_test_e2e_flags.sh has no `pattern=` line")


def _shell_matches(pattern: str, text: str) -> bool:
    """True if `grep -Eq` with the shell ERE matches `text`."""
    proc = subprocess.run(
        ["grep", "-Eq", "--", pattern],
        input=text,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _forbidden_flag_caught(visual_gate: ModuleType, snippet: str) -> bool:
    """True if BOTH the Python scanner and the shell pattern flag `snippet`.

    A ``block`` case must be caught on both surfaces (S5U-655 broadened them in
    lockstep); an ``allow`` case must be clean on both.
    """
    py_hit = bool(visual_gate._contains_forbidden_flag(snippet))
    sh_hit = _shell_matches(_shell_pattern(), snippet)
    assert py_hit == sh_hit, (
        f"Python scanner ({py_hit}) and shell pattern ({sh_hit}) disagree on "
        f"{snippet!r} — the two S5U-655 surfaces have drifted apart"
    )
    return py_hit


def _local_only_caught(visual_gate: ModuleType, snippet: str) -> bool:
    """True if any LOCAL_ONLY_SCRIPTS token regex matches `snippet`."""
    patterns = visual_gate._local_only_token_patterns()
    return any(pat.search(snippet) for pat in patterns.values())


def _segment_msgs(rule_a: ModuleType, snippet: str) -> list[str]:
    """Drift messages from the per-segment claim scan (S5U-676)."""
    msgs: list[str] = []
    for line in snippet.splitlines():
        msgs.extend(rule_a.scan_claim_drift(Path("DOC.md"), line, _AUTHORITATIVE_COUNT))
    return msgs


def _fence_slice_reaches(rule_e: ModuleType, snippet: str, target: str) -> bool:
    """True if the fence-aware _ci_section_body slice contains `target`."""
    body, _, _ = rule_e._ci_section_body(snippet)
    return target in body


def _assert_by_expect(expect: str, caught: bool, detail: str) -> None:
    """Common block/allow/known_residual assertion over a boolean ``caught``.

    ``block`` requires ``caught`` True; ``allow`` and ``known_residual`` both
    require it False (the detector stays silent), with distinct failure
    messages so a residual that closes points the author at promotion.
    """
    if expect == "block":
        assert caught, f"expected the detector to flag the snippet: {detail}"
    elif expect == "allow":
        assert not caught, f"expected the detector NOT to flag legitimate input: {detail}"
    else:  # known_residual
        assert not caught, (
            f"known_residual is no longer silent — the detector now catches "
            f"this; flip the case to `block`: {detail}"
        )


def _run_probe(
    case: CorpusCase,
    visual_gate: ModuleType,
    rule_a: ModuleType,
    rule_e: ModuleType,
) -> bool:
    """Drive the case's probe and return whether the detector caught it."""
    if case.probe == "forbidden_flag":
        return _forbidden_flag_caught(visual_gate, case.snippet)
    if case.probe == "local_only_token":
        return _local_only_caught(visual_gate, case.snippet)
    if case.probe == "segment_splitter":
        return len(_segment_msgs(rule_a, case.snippet)) >= 1
    if case.probe == "ci_section_fence":
        assert case.probe_target is not None, f"ci_section_fence case needs probe_target: {case.id}"
        reaches = _fence_slice_reaches(rule_e, case.snippet, case.probe_target)
        # For an `allow` fence case the slice must still contain the pre-heading
        # content (proving fence-awareness didn't break normal termination).
        if case.expect == "allow":
            body, _, _ = rule_e._ci_section_body(case.snippet)
            assert "9. local-only" in body, (
                f"allow case slice unexpectedly empty/wrong — expected the "
                f"pre-heading item present: [{case.id}]"
            )
        return reaches
    raise AssertionError(  # pragma: no cover - loader rejects unknown probes (G1)
        f"case {case.id} has no/unknown probe {case.probe!r}"
    )


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_boundary_shape_corpus_case(
    case: CorpusCase,
    visual_gate: ModuleType,
    rule_a: ModuleType,
    rule_e: ModuleType,
) -> None:
    detail = f"[{case.id}] {case.note or ''}".strip()
    caught = _run_probe(case, visual_gate, rule_a, rule_e)
    _assert_by_expect(case.expect, caught, detail)


def test_corpus_pins_named_regressions() -> None:
    """The named S5U regression cases must persist (no silent drop).

    ``load_corpus`` already fails closed on an empty case list; this pins the
    specific named bypass classes so a future refactor cannot drop them.
    """
    by_id = {c.id: c for c in _CASES}
    required_block = {
        "S5U-655-semicolon-after-short-flag",
        "S5U-655-ampersand-after-update-snapshots",
        "S5U-655-close-paren-after-ignore-snapshots",
        "S5U-655-local-only-semicolon-terminator",
        "S5U-676-stale-claim-in-prose-segment",
        "S5U-742-heading-inside-3-backtick-fence",
        "S5U-743-nested-4-backtick-wrapper",
    }
    missing = required_block - by_id.keys()
    assert not missing, f"corpus dropped regression case(s): {sorted(missing)}"
    for case_id in required_block:
        assert by_id[case_id].expect == "block", f"{case_id} must be a `block` case"
    # S5U-744 tilde fence is the documented open residual.
    assert "S5U-744-tilde-fence-not-honored" in by_id
    assert by_id["S5U-744-tilde-fence-not-honored"].expect == "known_residual"


def test_corpus_covers_every_expect_class() -> None:
    """A `block`, `allow`, and `known_residual` case must each be present.

    Guards against a corpus that silently degenerates into all-block (which would
    let a residual or false-positive guard go untracked).
    """
    expects = {c.expect for c in _CASES}
    assert {"block", "allow", "known_residual"} <= expects, f"missing expect class: {expects}"


def test_every_case_declares_a_probe() -> None:
    """Every boundary-shape case must name a probe (multi-detector corpus).

    A case with ``probe=None`` would have no detector to drive and silently
    skip — the loader allows ``None`` for the single-detector corpora, so this
    corpus-specific invariant is asserted here.
    """
    missing = [c.id for c in _CASES if c.probe is None]
    assert not missing, f"boundary-shape cases missing a `probe`: {missing}"
