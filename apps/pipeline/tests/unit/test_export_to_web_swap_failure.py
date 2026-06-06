"""Swap-time OSError cleanup + phantom-edition guard (S5U-899).

Follow-up to the S5U-890 two-phase commit. Two integrity-preserving gaps the
coordinator review of PR #393 surfaced:

* **Gap 1** — a swap-time ``OSError`` from ``_swap_dir``'s ``os.replace`` was
  re-raised bare from ``commit_staged`` and propagated uncaught past ``main``'s
  except clauses, so ``cleanup_staging`` never ran: this pid's ``.stage-*`` /
  ``.backup-*`` dirs were orphaned and the operator saw a traceback instead of a
  clean refusal. The fix wraps the rolled-back failure in ``ExportCommitError``
  so ``main`` runs cleanup + prints the refusal + exits non-zero.
* **Gap 2** — ``_build_document_index``'s edition comprehension did not skip
  ``.``-prefixed dir names, so an orphaned ``.backup-en-<pid>`` dir (which holds
  a ``manifest.json``) was listed as a phantom edition in ``index.json``. The
  fix mirrors the sibling document-dir loop's ``not d.name.startswith(".")``.

Shared fixture + seed helpers live in ``_two_phase_export_helpers``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from ._export_run_fixtures import init_registry
from ._two_phase_export_helpers import (
    documents_root_for,
    export_module,  # noqa: F401 — pytest fixture re-exported for collection
    no_swap_litter,
    seed_run,
    snapshot,
)


def test_swap_oserror_cleans_litter_and_refuses_without_traceback(
    export_module: ModuleType,  # noqa: F811 — pytest fixture injection
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Gap 1: a swap-time OSError is a clean refusal (SystemExit), no swap litter.

    A raw ``os.replace`` failure during the phase-3 swap must surface as the
    same ``Export refused`` / non-zero-exit path the other failure modes use,
    and must leave no ``.stage-*`` / ``.backup-*`` dirs next to the live bundle.
    Pre-fix the bare ``OSError`` escaped ``main`` uncaught (an uncaught
    exception, not ``SystemExit``) and skipped ``cleanup_staging``.
    """
    conn = init_registry(tmp_path / "registry.db")
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="en_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="en_a",
        page_text="EN-A",
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)

    # The commit module is loaded into sys.modules by the export_to_web import
    # (``from _export_commit import ...``). Patch the swap step (not os.replace,
    # which atomic writes also use during the staging build) so the phase-3 swap
    # raises OSError mid-commit_staged.
    commit_mod = sys.modules["_export_commit"]

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated swap failure")

    monkeypatch.setattr(commit_mod, "_swap_dir", _boom)

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "en_a"])
    assert exc.value.code == 1
    # No bundle was published (the EN edition never existed; swap failed on the
    # very first edition with nothing live to back up), and no swap scaffolding
    # remains next to the doc dir.
    assert snapshot(documents_root) == {}
    assert no_swap_litter(documents_root)


def test_swap_oserror_after_first_swap_rolls_back_and_cleans_litter(
    export_module: ModuleType,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Gap 1 (rollback path): a swap failure after one edition swapped restores it.

    Seeds a live EN bundle, then re-exports ``--edition all`` with the *second*
    ``os.replace`` failing. The first edition's swap must be rolled back from its
    backup (live bundle restored) and all this pid's staging/backup dirs removed
    — a clean ``SystemExit(1)`` refusal, not an uncaught traceback.
    """
    conn = init_registry(tmp_path / "registry.db")
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="en_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="en_a",
        page_text="EN-A",
    )
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="ru_a",
        started_at="2026-01-02T00:00:00",
        edition="ru",
        git_commit="ru_a",
        page_text="RU-A",
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)

    # Establish a live EN+RU bundle first (clean export).
    export_module.main(["--doc", "doc1", "--edition", "all"])
    good = snapshot(documents_root)
    assert good  # sanity: something is live

    commit_mod = sys.modules["_export_commit"]
    real_swap_dir = commit_mod._swap_dir
    calls = {"n": 0}

    def _flaky(staged: Path, live: Path, backup: Path) -> None:
        # Let the first edition swap through, then fail the second, simulating a
        # mid-commit OSError after one edition has already swapped (the rollback
        # path). Patch _swap_dir (not os.replace) so atomic writes during the
        # staging build are unaffected.
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated swap failure on second edition")
        real_swap_dir(staged, live, backup)

    monkeypatch.setattr(commit_mod, "_swap_dir", _flaky)

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "all"])
    assert exc.value.code == 1
    # The prior good bundle is restored intact and no swap litter remains.
    assert snapshot(documents_root) == good
    assert no_swap_litter(documents_root)


def test_backup_dir_is_not_listed_as_phantom_edition(
    export_module: ModuleType,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Gap 2: an orphaned ``.backup-*`` edition dir is absent from index.json.

    Seed a real EN edition plus an orphaned ``.backup-en-<oldpid>`` dir that
    (like a real edition dir) holds a ``manifest.json``. Pre-fix the edition
    comprehension listed it as an edition literally named ``.backup-en-99999``;
    post-fix the ``not d.name.startswith(".")`` filter skips it.
    """
    documents_root = documents_root_for(tmp_path)
    doc_dir = documents_root / "doc1"
    (doc_dir / "en").mkdir(parents=True)
    (doc_dir / "en" / "manifest.json").write_text("{}")
    # Orphan left by a prior swap-OSError of a different (old) pid.
    orphan = doc_dir / ".backup-en-99999"
    orphan.mkdir(parents=True)
    (orphan / "manifest.json").write_text("{}")

    entries = export_module._build_document_index(documents_root)

    assert entries == [{"document_id": "doc1", "editions": ["en"]}]
    editions = entries[0]["editions"]
    assert ".backup-en-99999" not in editions
    assert all(not name.startswith(".") for name in editions)
