"""Unit tests for the safety-gate corpus loader (S5U-921).

Covers the optional ``added_lines`` field added in S5U-921: the happy path (a
valid list models a real diff) and the Rule G1 fail-closed validation paths (a
malformed override must raise, never silently fall back to whole-snippet — which
would re-open the parametrize-corpus false-green).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ._safety_gate_corpus import load_corpus

_SNIPPET = """
import pytest


@pytest.mark.parametrize('a,b', [
    (1, 2),
    ('new_case', 99),
])
def test_x(a, b):
    pass
"""


def _write_corpus(tmp_path: Path, added_lines_literal: str | None) -> Path:
    """Write a one-case corpus; ``added_lines_literal`` is raw TOML or None."""
    body = [
        'policy = "demo_policy"',
        "[[case]]",
        'id = "c1"',
        'expect = "block"',
    ]
    if added_lines_literal is not None:
        body.append(f"added_lines = {added_lines_literal}")
    body.append(f'snippet = """{_SNIPPET}"""')
    corpus_dir = tmp_path / "safety_gate_corpus"
    corpus_dir.mkdir()
    path = corpus_dir / "demo_policy.toml"
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def _patched_corpus_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``corpus_dir()`` at a tmp dir so load_corpus reads our fixture."""
    monkeypatch.setattr(
        "tests.unit._safety_gate_corpus.corpus_dir",
        lambda: tmp_path / "safety_gate_corpus",
    )
    return tmp_path


def test_added_lines_absent_is_none(_patched_corpus_dir: Path) -> None:
    _write_corpus(_patched_corpus_dir, None)
    (case,) = load_corpus("demo_policy")
    assert case.added_lines is None


def test_added_lines_valid_list_parses(_patched_corpus_dir: Path) -> None:
    _write_corpus(_patched_corpus_dir, "[6]")
    (case,) = load_corpus("demo_policy")
    assert case.added_lines == (6,)


def test_added_lines_empty_list_fails_closed(_patched_corpus_dir: Path) -> None:
    _write_corpus(_patched_corpus_dir, "[]")
    with pytest.raises(ValueError, match="non-empty list"):
        load_corpus("demo_policy")


def test_added_lines_non_int_entry_fails_closed(_patched_corpus_dir: Path) -> None:
    _write_corpus(_patched_corpus_dir, '["6"]')
    with pytest.raises(ValueError, match="not an int line number"):
        load_corpus("demo_policy")


def test_added_lines_bool_entry_fails_closed(_patched_corpus_dir: Path) -> None:
    # bool is an int subclass; `[true]` must NOT masquerade as line 1.
    _write_corpus(_patched_corpus_dir, "[true]")
    with pytest.raises(ValueError, match="not an int line number"):
        load_corpus("demo_policy")


def test_added_lines_out_of_range_fails_closed(_patched_corpus_dir: Path) -> None:
    _write_corpus(_patched_corpus_dir, "[999]")
    with pytest.raises(ValueError, match="out of range"):
        load_corpus("demo_policy")


def test_added_lines_zero_fails_closed(_patched_corpus_dir: Path) -> None:
    _write_corpus(_patched_corpus_dir, "[0]")
    with pytest.raises(ValueError, match="out of range"):
        load_corpus("demo_policy")


def test_added_lines_scalar_not_list_fails_closed(_patched_corpus_dir: Path) -> None:
    _write_corpus(_patched_corpus_dir, "6")
    with pytest.raises(ValueError, match="non-empty list"):
        load_corpus("demo_policy")


# ---------------------------------------------------------------------------
# probe enum (S5U-820 added the instruction-drift family probe values). The
# loader validates `probe` against VALID_PROBE and fails closed (Rule G1) on an
# unknown value — never silently degrading a multi-detector case to the
# whole-snippet single-detector path.
# ---------------------------------------------------------------------------


def _write_probe_corpus(tmp_path: Path, probe_literal: str) -> None:
    """Write a one-case corpus carrying a raw TOML ``probe`` value."""
    body = "\n".join(
        [
            'policy = "demo_policy"',
            "[[case]]",
            'id = "c1"',
            'expect = "block"',
            f"probe = {probe_literal}",
            'snippet = "x"',
        ]
    )
    corpus_dir = tmp_path / "safety_gate_corpus"
    corpus_dir.mkdir()
    (corpus_dir / "demo_policy.toml").write_text(body + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    "probe",
    [
        "claim_count",
        "retired_term",
        "safety_gate_scope",
        "ci_gate_count",
        "ci_inline_enum",
        "tilde_fence",
        "tomli_arm",
    ],
)
def test_instruction_drift_probe_values_validate(_patched_corpus_dir: Path, probe: str) -> None:
    """Each S5U-820 instruction-drift probe value is accepted by the loader."""
    _write_probe_corpus(_patched_corpus_dir, f'"{probe}"')
    (case,) = load_corpus("demo_policy")
    assert case.probe == probe


def test_unknown_probe_fails_closed(_patched_corpus_dir: Path) -> None:
    """An unknown probe value raises rather than silently degrading (Rule G1)."""
    _write_probe_corpus(_patched_corpus_dir, '"not_a_real_probe"')
    with pytest.raises(ValueError, match="unknown probe"):
        load_corpus("demo_policy")
