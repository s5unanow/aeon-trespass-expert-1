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
