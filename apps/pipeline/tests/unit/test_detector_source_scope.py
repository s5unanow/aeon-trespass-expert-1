"""Unit tests for scripts/_detector_source_scope.py (S5U-922).

The helper computes the content-derived safety-gate scope: the UNION of every
corpus's ``detector_sources`` list. Both the pre-PR hook and the post-merge
audit consume it so a future extracted detector helper (e.g.
``scripts/_parametrize_ast.py``) is in safety-gate scope without a regex edit.

Covers:
- Rule G2 happy-path: the real-repo union contains the extracted detector
  helpers and excludes benign underscore helpers (no over-capture).
- Rule G1 fail-closed: unparseable corpus, missing ``detector_sources``, and a
  non-string entry each raise ``DetectorScopeError`` / exit the CLI non-zero.
- Absent-corpus-dir degrades to an empty set (synthetic-repo carve-out).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "_detector_source_scope.py"


def _load() -> ModuleType:
    if str(REPO / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("_detector_source_scope", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_corpus(corpus_dir: Path, name: str, body: str) -> None:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / name).write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# G2 happy-path: real-repo union (content-derived, no over-capture)
# ---------------------------------------------------------------------------


def test_real_corpus_union_includes_extracted_detector_helpers() -> None:
    """G2: the escaping underscore detector helpers ARE in the content-derived set.

    This is the S5U-922 fix: pre-fix the safety-gate matchers were name-derived
    and missed these. The union must include them.
    """
    mod = _load()
    scope = mod.detector_source_scope(repo_root=REPO)
    assert "scripts/_parametrize_ast.py" in scope
    # The six instruction-drift rule helpers that also escape the name regex.
    for letter in ("a", "b", "c", "e", "f", "g"):
        assert f"scripts/_instruction_drift_rule_{letter}.py" in scope


def test_real_corpus_union_excludes_benign_underscore_helpers() -> None:
    """G2: a name-pattern broadening would over-capture these; content-derived does not."""
    mod = _load()
    scope = mod.detector_source_scope(repo_root=REPO)
    for benign in (
        "scripts/_export_blocks.py",
        "scripts/_golden_pipeline_payloads.py",
        "scripts/_linear_client.py",
        "scripts/_instruction_drift_rule_d.py",  # rule D is NOT a detector_source
    ):
        assert benign not in scope, f"{benign} should NOT be over-captured"


# ---------------------------------------------------------------------------
# Absent corpus dir → empty set (synthetic-repo carve-out)
# ---------------------------------------------------------------------------


def test_absent_corpus_dir_returns_empty_set(tmp_path: Path) -> None:
    """A repo root with no corpus dir yields an empty set (not an error).

    This keeps the synthetic-repo audit tests (which use tmp_path repos with no
    corpus) green, while the real-repo callers always have the corpus dir.
    """
    mod = _load()
    assert mod.detector_source_scope(repo_root=tmp_path) == frozenset()


# ---------------------------------------------------------------------------
# G1 fail-closed degenerate inputs
# ---------------------------------------------------------------------------


def test_unparseable_corpus_fails_closed(tmp_path: Path) -> None:
    """G1: a corpus TOML that does not parse raises DetectorScopeError."""
    mod = _load()
    corpus = tmp_path / "apps" / "pipeline" / "tests" / "safety_gate_corpus"
    _write_corpus(corpus, "broken.toml", "this is = = not valid toml [[[")
    with pytest.raises(mod.DetectorScopeError, match="cannot parse corpus"):
        mod.detector_source_scope(repo_root=tmp_path)


def test_missing_detector_sources_fails_closed(tmp_path: Path) -> None:
    """G1: a corpus without a non-empty detector_sources list fails closed."""
    mod = _load()
    corpus = tmp_path / "apps" / "pipeline" / "tests" / "safety_gate_corpus"
    _write_corpus(corpus, "no_sources.toml", 'policy = "x"\n')
    with pytest.raises(mod.DetectorScopeError, match="missing a non-empty"):
        mod.detector_source_scope(repo_root=tmp_path)


def test_empty_detector_sources_fails_closed(tmp_path: Path) -> None:
    """G1: an empty detector_sources list fails closed."""
    mod = _load()
    corpus = tmp_path / "apps" / "pipeline" / "tests" / "safety_gate_corpus"
    _write_corpus(corpus, "empty_sources.toml", 'policy = "x"\ndetector_sources = []\n')
    with pytest.raises(mod.DetectorScopeError, match="missing a non-empty"):
        mod.detector_source_scope(repo_root=tmp_path)


def test_non_string_detector_source_entry_fails_closed(tmp_path: Path) -> None:
    """G1: a non-string detector_sources entry fails closed."""
    mod = _load()
    corpus = tmp_path / "apps" / "pipeline" / "tests" / "safety_gate_corpus"
    _write_corpus(corpus, "bad_entry.toml", 'policy = "x"\ndetector_sources = [42]\n')
    with pytest.raises(mod.DetectorScopeError, match="non-string/empty"):
        mod.detector_source_scope(repo_root=tmp_path)


# ---------------------------------------------------------------------------
# CLI behavior
# ---------------------------------------------------------------------------


def test_cli_list_prints_union(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --list prints one in-scope path per line and exits 0."""
    mod = _load()
    rc = mod.main(["--list", "--repo-root", str(REPO)])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert "scripts/_parametrize_ast.py" in out


def test_cli_fails_closed_on_malformed_corpus(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """G1: CLI exits non-zero (and prints to stderr) on a malformed corpus."""
    mod = _load()
    corpus = tmp_path / "apps" / "pipeline" / "tests" / "safety_gate_corpus"
    _write_corpus(corpus, "broken.toml", "= = invalid [[[")
    rc = mod.main(["--list", "--repo-root", str(tmp_path)])
    assert rc == 1
    assert "BLOCKED" in capsys.readouterr().err
