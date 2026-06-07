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


def test_corpus_layer_excludes_import_only_helpers() -> None:
    """The CORPUS layer alone does not declare the import-only helpers.

    This pins the layer boundary: `_linear_client` / `_instruction_drift_rule_d`
    are NOT in the corpus `detector_sources` union — they reach scope only via the
    import-graph layer (asserted separately). A future PR that wants the corpus
    layer to also declare them is free to, but the safety guarantee must not
    depend on it (that dependency was the S5U-926 bug).
    """
    mod = _load()
    corpus = mod.corpus_source_scope(repo_root=REPO)
    assert "scripts/_linear_client.py" not in corpus
    assert "scripts/_instruction_drift_rule_d.py" not in corpus


def test_full_scope_includes_load_bearing_import_only_helpers() -> None:
    """S5U-926: helpers imported by an in-scope detector but NOT in any corpus.

    Reverses the S5U-922 assumption (the prior version of this file asserted
    `_linear_client` / `_instruction_drift_rule_d` were "benign / NOT
    over-captured"). The import-graph layer now folds every load-bearing helper
    imported by a `check_*`/`pre-*` detector into the full scope.
    """
    mod = _load()
    scope = mod.detector_source_scope(repo_root=REPO)
    for helper in (
        "scripts/_instruction_drift_rule_d.py",  # imported by check_instruction_drift
        "scripts/_erosion_report_fmt.py",  # imported by check_code_erosion
        "scripts/_hotspot_budgets.py",  # imported by check_code_erosion
        "scripts/_repo_summary.py",  # imported by check_code_erosion
        "scripts/_linear_client.py",  # imported by check_coverage_table
    ):
        assert helper in scope, f"{helper} must be in the content-derived scope"


def test_real_scope_excludes_non_imported_underscore_helpers() -> None:
    """G2: a name-pattern broadening would over-capture these; content-derived does not.

    These helpers are neither declared in a corpus nor imported by any in-scope
    detector, so they stay OUT of the full scope — the import-graph layer does
    not over-capture.
    """
    mod = _load()
    scope = mod.detector_source_scope(repo_root=REPO)
    for benign in (
        "scripts/_export_blocks.py",
        "scripts/_golden_pipeline_payloads.py",
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
# S5U-926: import-graph layer (synthetic repos)
# ---------------------------------------------------------------------------


def _write_script(scripts_dir: Path, name: str, body: str) -> None:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / name).write_text(body, encoding="utf-8")


def test_import_graph_captures_directly_imported_helper(tmp_path: Path) -> None:
    """A sibling _helper imported by a check_* detector is captured."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "from _foo_helper import bar\n")
    _write_script(scripts, "_foo_helper.py", "def bar() -> None: ...\n")
    scope = mod.import_graph_scope(repo_root=tmp_path)
    assert scope == frozenset({"scripts/_foo_helper.py"})


def test_import_graph_captures_transitive_helper(tmp_path: Path) -> None:
    """A helper imported only by another helper (not a detector) is captured."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "from _foo_helper import bar\n")
    _write_script(scripts, "_foo_helper.py", "from _deep_helper import baz\n")
    _write_script(scripts, "_deep_helper.py", "def baz() -> None: ...\n")
    scope = mod.import_graph_scope(repo_root=tmp_path)
    assert scope == frozenset({"scripts/_foo_helper.py", "scripts/_deep_helper.py"})


def test_import_graph_captures_type_checking_and_aliased_imports(tmp_path: Path) -> None:
    """TYPE_CHECKING-guarded and `import _x as y` imports are still captured (AST)."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "from typing import TYPE_CHECKING\n"
        "import _aliased as al\n"
        "if TYPE_CHECKING:\n"
        "    from _typecheck_only import T\n",
    )
    _write_script(scripts, "_aliased.py", "X = 1\n")
    _write_script(scripts, "_typecheck_only.py", "T = int\n")
    scope = mod.import_graph_scope(repo_root=tmp_path)
    assert scope == frozenset({"scripts/_aliased.py", "scripts/_typecheck_only.py"})


def test_import_graph_excludes_future_stdlib_and_thirdparty(tmp_path: Path) -> None:
    """`__future__`, stdlib, and third-party imports are NOT captured (no scripts/X.py)."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(
        scripts,
        "check_foo.py",
        "from __future__ import annotations\nimport os\nimport re\nimport pydantic\n",
    )
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_import_graph_excludes_non_imported_helper(tmp_path: Path) -> None:
    """A sibling _helper that no detector imports stays OUT (no over-capture)."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "import os\n")
    _write_script(scripts, "_unused_helper.py", "X = 1\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_import_graph_ignores_underscore_import_without_sibling_file(tmp_path: Path) -> None:
    """An `import _ghost` with no scripts/_ghost.py resolves to nothing (no phantom)."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "import _ghost\n")
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_import_graph_absent_scripts_dir_returns_empty_set(tmp_path: Path) -> None:
    """Absent scripts/ dir degrades to empty set (synthetic-repo carve-out, G1 carve)."""
    mod = _load()
    assert mod.import_graph_scope(repo_root=tmp_path) == frozenset()


def test_import_graph_unparseable_detector_fails_closed(tmp_path: Path) -> None:
    """G1: a detector source with a SyntaxError fails closed."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "def broken(:\n")  # syntax error
    with pytest.raises(mod.DetectorScopeError, match="cannot parse detector source"):
        mod.import_graph_scope(repo_root=tmp_path)


def test_import_graph_unparseable_helper_fails_closed(tmp_path: Path) -> None:
    """G1: a transitively-reached helper with a SyntaxError fails closed."""
    mod = _load()
    scripts = tmp_path / "scripts"
    _write_script(scripts, "check_foo.py", "from _bad_helper import x\n")
    _write_script(scripts, "_bad_helper.py", "def broken(:\n")  # syntax error
    with pytest.raises(mod.DetectorScopeError, match="cannot parse detector source"):
        mod.import_graph_scope(repo_root=tmp_path)


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
