"""Corpus-driven contract test for the hook-bypass token detector (S5U-822).

S5U-789 child. Drives the REAL ``scan(text)`` production entry point of
``scripts/check_hook_bypass_tokens.py`` over every case in
``apps/pipeline/tests/safety_gate_corpus/hook_bypass.toml``:

* ``block``          → ``scan()`` must return >=1 violation (token caught).
* ``allow``          → ``scan()`` must return 0 violations.
* ``known_residual`` → ``scan()`` returns 0 today; pinned so a future detector
  upgrade that closes the residual surfaces here and the case can flip to
  ``block``.

The corpus is the contract (S5U-789): a reviewer-found bypass is added as a
``block`` case here, not patched in as a one-off regex.
``scripts/check_detector_corpus_coverage.py`` fails CI if the detector source
changes without a change to the corpus file.

CI-gating decision (S5U-822, recorded in ``.claude/rules/hooks.md``): this
contract test runs inside the existing ``python / test`` job. The detector is
defense-in-depth; it is NOT a new required-check context, and the review.md #22
prose probe stays as the merge-time reviewer gate.

Red-before confirmation: ran the contract test at HEAD with the detector's
``scan()`` body stubbed to ``return []`` (a permissive detector, modelling the
prose-only pre-S5U-822 state) — every ``block`` case failed
("expected >=1 violation but got none"). Restoring the real ``scan()`` turns
them green. Captured excerpt and method in ``tmp/plan-s5u-822.md`` §7 and the
PR body. The G1 ``main()`` degenerate-input tests (no input / unreadable file /
bad commit-range) assert exit code 2 and a file-naming message; reverting the
fail-closed ``RuntimeError`` raises to a silent ``return []`` makes
``test_main_no_input_fails_closed`` fail (exit 0 instead of 2).
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

_CASES = load_corpus("hook_bypass")

# Every hooks.md "Hook-bypass token enumeration" token must keep a `block` case
# so a future refactor cannot silently drop a vector's coverage. Keyed by corpus
# case id; the value is the hooks.md entry it pins.
_REQUIRED_BLOCK_IDS = {
    "cli-no-verify": "CLI: git commit --no-verify",
    "cli-amend-no-verify": "CLI: git commit --amend --no-verify",
    "cli-short-n": "CLI: git commit -n",
    "env-husky-0": "env: HUSKY=0",
    "env-lefthook-0": "env: LEFTHOOK=0",
    "env-skip-hook": "env: SKIP=<hook>",
    "env-hook-bypass": "env: HOOK_BYPASS=",
    "env-no-verify-var": "env: NO_VERIFY=",
    "env-coordinator-ack-source": "env: COORDINATOR_ACK_STATUS_SOURCE=",
    "mut-chmod-x": "mutation: chmod -x .git/hooks/pre-commit",
    "mut-rm-hook": "mutation: rm .git/hooks/pre-commit",
    "mut-noop-replace": "mutation: no-op exit 0 replacement",
    "redirect-config-hookspath": "redirect: git config core.hooksPath",
    "redirect-c-hookspath": "redirect: git -c core.hooksPath=",
}


def _load_detector(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import scripts/check_hook_bypass_tokens.py as a fresh module."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    path = SCRIPT_DIR / "check_hook_bypass_tokens.py"
    spec = importlib.util.spec_from_file_location("check_hook_bypass_tokens", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_hook_bypass_tokens"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def detector(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Fresh import of the hook-bypass detector per test."""
    yield _load_detector(monkeypatch)
    sys.modules.pop("check_hook_bypass_tokens", None)


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_hook_bypass_corpus_case(detector: ModuleType, case: CorpusCase) -> None:
    violations = detector.scan(case.snippet)
    rendered = [v.format() for v in violations]
    detail = f"[{case.id}] {case.note or ''}".strip()

    if case.expect == "block":
        assert len(violations) >= 1, f"expected >=1 violation but got none: {detail}"
    else:
        # allow OR known_residual: the detector must stay silent.
        assert violations == [], (
            f"expected 0 violations ({case.expect}) but got {rendered}: {detail}"
        )


def test_corpus_pins_every_hooks_md_token() -> None:
    """Every hooks.md enumeration token keeps a `block` case (no silent drop).

    ``load_corpus`` already fails closed on an empty case list; this pins the
    specific named token vectors so a future refactor cannot drop one's coverage.
    """
    by_id = {c.id: c for c in _CASES}
    missing = set(_REQUIRED_BLOCK_IDS) - by_id.keys()
    assert not missing, f"corpus dropped required token case(s): {sorted(missing)}"
    for case_id in _REQUIRED_BLOCK_IDS:
        assert by_id[case_id].expect == "block", (
            f"{case_id} pins '{_REQUIRED_BLOCK_IDS[case_id]}' and must be a `block` case"
        )


def test_corpus_covers_allow_and_residual_classes() -> None:
    """A `block`, `allow`, and `known_residual` case must each be present.

    Guards against a corpus that silently degenerates into all-block (which would
    let the documented non-matching paraphrases and out-of-scope residuals go
    untracked).
    """
    expects = {c.expect for c in _CASES}
    assert {"block", "allow", "known_residual"} <= expects, f"missing expect class: {expects}"


def test_documented_residuals_present() -> None:
    """The two hooks.md out-of-scope forms stay pinned as `known_residual`.

    If a future on-disk-config or multi-line detector closes one of these, the
    corpus case flips red here (no longer silent) and must be promoted to
    `block`.
    """
    by_id = {c.id: c for c in _CASES}
    for residual_id in ("residual-gitconfig-file-form", "residual-crossline-mutation-prose"):
        assert residual_id in by_id, f"corpus dropped residual case {residual_id!r}"
        assert by_id[residual_id].expect == "known_residual", (
            f"{residual_id} must stay `known_residual` until the detector closes it"
        )


# --------------------------------------------------------------------------- #
# G1 fail-closed (.claude/rules/guards.md): main() must exit non-zero on a      #
# degenerate input rather than silently pass "no tokens". Co-located with the   #
# detector's own contract test per Rule G1 "co-located with the script".       #
# --------------------------------------------------------------------------- #


def test_main_no_input_fails_closed(
    detector: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """No input source (no file, no range, no stdin) → exit 2, not a blind pass."""
    rc = detector.main([])
    assert rc == 2, "main() must fail closed (exit 2) when given no input"
    err = capsys.readouterr().err
    assert "no input" in err.lower()


def test_main_unreadable_text_file_fails_closed(
    detector: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unreadable --text-file → exit 2 with a message naming the file."""
    missing = tmp_path / "does-not-exist.md"
    rc = detector.main(["--text-file", str(missing)])
    assert rc == 2, "main() must fail closed (exit 2) on an unreadable --text-file"
    err = capsys.readouterr().err
    assert str(missing) in err


def test_main_bad_commit_range_fails_closed(
    detector: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unresolvable --commit-range (run outside any repo) → exit 2.

    ``git log`` returns non-zero; the detector must surface that and fail closed,
    not return empty text and report "clean".
    """
    rc = detector.main(["--commit-range", "definitely-not-a-ref..also-not-a-ref"])
    assert rc == 2, "main() must fail closed (exit 2) on an unresolvable --commit-range"
    err = capsys.readouterr().err
    assert "git log failed" in err


def test_main_clean_text_passes(
    detector: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean --text-file with no bypass token → exit 0 with a clean message."""
    clean = tmp_path / "clean.md"
    clean.write_text("S5U-822: add hook-bypass detector and corpus\n", encoding="utf-8")
    rc = detector.main(["--text-file", str(clean)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "clean" in out


def test_main_token_text_fails(
    detector: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A --text-file containing a bypass token → exit 1 with the violation."""
    bad = tmp_path / "bad.md"
    bad.write_text("git commit --no-verify -m 'wip'\n", encoding="utf-8")
    rc = detector.main(["--text-file", str(bad)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "cli_no_verify" in err
