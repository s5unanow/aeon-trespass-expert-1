"""Tests for scripts/check_file_length.py (S5U-663).

Unifies the 400-line file-length ceiling across source and test code. The
scanner previously skipped test directories (`apps/pipeline/tests`,
`apps/web/tests`) entirely; S5U-663 adds them to ``DEFAULT_DIRS`` and
grandfathers the 14 test files that already exceeded the ceiling.

Three-input adversarial coverage (see `tmp/plan-s5u-663.md` §3):

* Happy path — files at 399/400 lines pass.
* Failure path — a 401-line file fails.
* Boundary — exactly-at-limit (400 lines) passes; 401 fails.
* Grandfather — a file in ``KNOWN_VIOLATORS`` is skipped even if over limit.
* Scan-coverage — ``find_source_files`` actually yields paths under
  ``apps/pipeline/tests/`` (the bug S5U-663 closes). Red-before anchor.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_file_length.py"


@pytest.fixture()
def cfl(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import check_file_length.py as a module."""
    monkeypatch.syspath_prepend(str(SCRIPT_PATH.parent))
    spec = importlib.util.spec_from_file_location("check_file_length", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_file_length"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("check_file_length", None)


# ---------------------------------------------------------------------------
# Red-before anchor: test directories are in the scan
# ---------------------------------------------------------------------------


def test_test_directories_are_scanned(cfl: ModuleType) -> None:
    """``DEFAULT_DIRS`` must cover test trees (S5U-663).

    Red-before confirmation: commit 7d30bf5371137c8115f69066496c3e8a9060f2fd
    (pre-fix main HEAD) shows ``DEFAULT_DIRS`` as only
    ``[apps/pipeline/src, packages/schemas/python, scripts, apps/web/src]``
    — this assertion fails with "apps/pipeline/tests not in DEFAULT_DIRS".
    The scan-coverage test below is a stronger red-before: running it
    against the pre-fix script yields zero paths under
    ``apps/pipeline/tests/`` from ``find_source_files``.
    """
    assert "apps/pipeline/tests" in cfl.DEFAULT_DIRS
    assert "apps/web/tests" in cfl.DEFAULT_DIRS


def test_find_source_files_includes_test_paths(cfl: ModuleType) -> None:
    """``find_source_files`` yields at least one path under
    ``apps/pipeline/tests/`` in the real tree.

    Red-before confirmation: commit 7d30bf5371137c8115f69066496c3e8a9060f2fd
    — ``find_source_files(REPO)`` returned zero paths with
    ``apps/pipeline/tests`` in them (the implicit exclusion). After the
    S5U-663 fix, at least one path is yielded.
    """
    files = cfl.find_source_files(REPO)
    rel_strs = [str(f.relative_to(REPO)) for f in files]
    assert any(r.startswith("apps/pipeline/tests/") for r in rel_strs), (
        "S5U-663 regression — test directories are not being scanned"
    )


# ---------------------------------------------------------------------------
# Boundary / threshold (pins existing check_files invariants)
# ---------------------------------------------------------------------------


def _write_lines(path: Path, n: int) -> None:
    """Write ``n`` lines (each a single character) to ``path``."""
    path.write_text("x\n" * n)


def test_exact_limit_passes(cfl: ModuleType, tmp_path: Path) -> None:
    """400-line file at the limit passes (``>`` not ``>=``).

    Red-before confirmation: N/A — no production code change in this PR
    for this branch; test documents existing invariant; reviewer asked to
    cross-check diff.
    """
    f = tmp_path / "foo.py"
    _write_lines(f, 400)
    errors = cfl.check_files([f], max_lines=400, root=tmp_path)
    assert errors == []


def test_over_limit_fails(cfl: ModuleType, tmp_path: Path) -> None:
    """401-line file fails; error message cites the count.

    Red-before confirmation: N/A — no production code change in this PR
    for this branch; test documents existing invariant.
    """
    f = tmp_path / "foo.py"
    _write_lines(f, 401)
    errors = cfl.check_files([f], max_lines=400, root=tmp_path)
    assert len(errors) == 1
    assert "401 lines" in errors[0]
    assert "foo.py" in errors[0]


def test_under_limit_passes(cfl: ModuleType, tmp_path: Path) -> None:
    """399-line file passes.

    Red-before confirmation: N/A — no production code change in this PR
    for this branch; test documents existing invariant.
    """
    f = tmp_path / "foo.py"
    _write_lines(f, 399)
    errors = cfl.check_files([f], max_lines=400, root=tmp_path)
    assert errors == []


# ---------------------------------------------------------------------------
# Grandfather allowlist (pins S5U-663 behavior)
# ---------------------------------------------------------------------------


def test_grandfathered_file_is_skipped(cfl: ModuleType, tmp_path: Path) -> None:
    """A file whose relative path is in ``KNOWN_VIOLATORS`` passes even
    when over the limit.

    Red-before confirmation: N/A — pins existing ``KNOWN_VIOLATORS``
    invariant; no production change here.
    """
    # Use an existing grandfathered entry as the target relative path.
    rel = "apps/pipeline/tests/unit/test_check_visual_gate_scope.py"
    assert rel in cfl.KNOWN_VIOLATORS
    abs_path = tmp_path / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    _write_lines(abs_path, 9999)
    errors = cfl.check_files([abs_path], max_lines=400, root=tmp_path)
    assert errors == [], (
        "S5U-663 grandfather allowlist failure — allowlisted path should skip the length check"
    )


def test_grandfather_covers_known_violators(cfl: ModuleType) -> None:
    """Every test file currently over 400 lines is either in
    ``KNOWN_VIOLATORS`` or fails the scan.

    Red-before confirmation: commit 7d30bf5371137c8115f69066496c3e8a9060f2fd
    — pre-fix, ``make lint`` passed with 14 over-limit test files because
    they were never scanned. Post-fix, the same ``make lint`` must still
    pass, which means every one of those 14 paths is allowlisted. This
    test locks in that coverage; removing an entry from KNOWN_VIOLATORS
    without splitting the file fails the ``make lint`` gate.
    """
    files = cfl.find_source_files(REPO)
    errors = cfl.check_files(files, max_lines=400, root=REPO)
    assert errors == [], "S5U-663 — over-limit file not in grandfather list: " + "; ".join(errors)


# ---------------------------------------------------------------------------
# G1 fail-closed: non-existent path raises loudly
# ---------------------------------------------------------------------------


def test_nonexistent_file_raises(cfl: ModuleType, tmp_path: Path) -> None:
    """Passing a path that does not exist raises ``FileNotFoundError``
    (fail-closed, not silent skip).

    Red-before confirmation: N/A — pins existing behavior inherited from
    ``Path.read_text``. Documents the S5U-661 G1 invariant for this
    scanner.
    """
    missing = tmp_path / "does-not-exist.py"
    with pytest.raises(FileNotFoundError):
        cfl.check_files([missing], max_lines=400, root=tmp_path)


# ---------------------------------------------------------------------------
# Adversarial: test-directory enforcement catches a new over-limit test
# ---------------------------------------------------------------------------


def test_new_oversized_test_file_is_rejected(cfl: ModuleType, tmp_path: Path) -> None:
    """A freshly-added test file over the ceiling that is NOT in
    ``KNOWN_VIOLATORS`` must fail the scan.

    This is the canonical regression S5U-663 closes: before the fix,
    ``apps/pipeline/tests/test_new_oversized.py @ 900 lines`` would merge
    silently because the directory was never scanned. After the fix, the
    same file fails unless explicitly allowlisted.

    Red-before confirmation: commit 7d30bf5371137c8115f69066496c3e8a9060f2fd
    — ``find_source_files(tmp_path)`` with ``apps/pipeline/tests/`` laid
    out under ``tmp_path`` returned zero files because ``DEFAULT_DIRS``
    did not include that prefix. After S5U-663 it returns the dummy file
    and ``check_files`` flags it.
    """
    rel = "apps/pipeline/tests/unit/test_new_oversized.py"
    assert rel not in cfl.KNOWN_VIOLATORS, "Sentinel path must not be allowlisted"
    abs_path = tmp_path / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    _write_lines(abs_path, 900)

    # Simulate the default scan against a fake repo root at tmp_path.
    files = cfl.find_source_files(tmp_path)
    rel_found = [str(f.relative_to(tmp_path)) for f in files]
    assert rel in rel_found, "S5U-663 — test directory must be scanned under DEFAULT_DIRS"
    errors = cfl.check_files(files, max_lines=400, root=tmp_path)
    assert any(rel in e and "900 lines" in e for e in errors), (
        "S5U-663 — over-limit test file was not flagged: " + "; ".join(errors)
    )
