"""Ref-bound QA export behaviour (S5U-869).

In run-bound mode ``export_qa`` must never fall back to the legacy mtime
directory scan: a supplied ``summary_path`` is exported verbatim, and
``summary_path=None`` with ``ref_bound=True`` means the resolved run carried no
QA artifact → skip, **not** mtime-splice a different run's summary into the
bundle. This is the QA half of the cross-run-splice hazard the issue closes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "_export_qa.py"


@pytest.fixture()
def qa_module() -> Iterator[ModuleType]:
    """Import _export_qa.py as a module."""
    spec = importlib.util.spec_from_file_location("_export_qa_refbound_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_qa_refbound_test"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_qa_refbound_test", None)


def _seed_stray_summary(artifact_root: Path, doc_id: str) -> None:
    """Seed a summary in the canonical QA dir that mtime-scan would otherwise find."""
    summary = {
        "schema_version": "qa_summary.v1",
        "document_id": doc_id,
        "run_id": "run_stray",
        "edition": "ru",
        "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
        "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
        "blocking": False,
        "record_refs": [],
        "review_pack_ref": "",
    }
    path = artifact_root / doc_id / "qa" / "document" / doc_id / "stray.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary))


def test_ref_bound_none_summary_skips_without_mtime_fallback(
    qa_module: ModuleType, tmp_path: Path
) -> None:
    """ref_bound=True + summary_path=None must skip QA, NOT scan the QA dir."""
    doc_id = "doc1"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    # A stray summary exists in the canonical dir — mtime scan would pick it.
    _seed_stray_summary(artifact_root, doc_id)

    count = qa_module.export_qa(
        artifact_root, doc_id, "ru", doc_public, summary_path=None, ref_bound=True
    )

    assert count == 0
    # The stray summary must NOT have been spliced into the bundle.
    assert not (doc_public / "ru" / "data" / "qa_summary.json").exists()


def test_legacy_none_summary_still_scans_dir(qa_module: ModuleType, tmp_path: Path) -> None:
    """ref_bound=False (legacy) + summary_path=None preserves the directory scan."""
    doc_id = "doc1"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    _seed_stray_summary(artifact_root, doc_id)

    qa_module.export_qa(artifact_root, doc_id, "ru", doc_public)  # ref_bound defaults False

    # Legacy path DOES scan and export the summary (backward-compat behaviour).
    assert (doc_public / "ru" / "data" / "qa_summary.json").exists()


def test_ref_bound_none_summary_removes_stale_qa_companions(
    qa_module: ModuleType, tmp_path: Path
) -> None:
    """S5U-892: ref_bound + summary_path=None must DELETE prior-run QA companions.

    The reader fetches ``qa_summary.json`` / ``qa_records.json`` /
    ``qa_metrics.json`` at fixed paths, so a run that carries no QA must not
    leave a prior run's files in place (cross-run splice).
    """
    doc_id = "doc1"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    out_dir = doc_public / "ru" / "data"
    out_dir.mkdir(parents=True)
    # Plant stale companions from a prior run's export.
    (out_dir / "qa_summary.json").write_text(json.dumps({"run_id": "run_a"}))
    (out_dir / "qa_records.json").write_text(json.dumps({"records": []}))
    (out_dir / "qa_metrics.json").write_text(json.dumps({"run_id": "run_a"}))

    count = qa_module.export_qa(
        artifact_root, doc_id, "ru", doc_public, summary_path=None, ref_bound=True
    )

    assert count == 0
    assert not (out_dir / "qa_summary.json").exists()
    assert not (out_dir / "qa_records.json").exists()
    assert not (out_dir / "qa_metrics.json").exists()


def test_summary_without_metrics_removes_stale_qa_metrics(
    qa_module: ModuleType, tmp_path: Path
) -> None:
    """S5U-892: a run whose summary carries QA but no metrics must drop stale qa_metrics.json.

    Models a re-export where run B has a QA summary but no metrics artifact
    (legacy summary, no ``qa_metrics_ref``). Run A's ``qa_metrics.json`` must be
    removed; the freshly-written ``qa_summary.json`` / ``qa_records.json``
    overwrite run A's in place.
    """
    doc_id = "doc1"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    out_dir = doc_public / "ru" / "data"
    out_dir.mkdir(parents=True)
    (out_dir / "qa_metrics.json").write_text(json.dumps({"run_id": "run_a"}))

    bound = artifact_root / doc_id / "qa" / "document" / doc_id / "run_b.json"
    bound.parent.mkdir(parents=True, exist_ok=True)
    bound.write_text(
        json.dumps(
            {
                "schema_version": "qa_summary.v1",
                "document_id": doc_id,
                "run_id": "run_b",
                "edition": "ru",
                "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "blocking": False,
                "record_refs": [],
                "review_pack_ref": "",
            }
        )
    )

    qa_module.export_qa(artifact_root, doc_id, "ru", doc_public, summary_path=bound, ref_bound=True)

    # Summary/records were (re)written; the stale metrics file is gone.
    assert (out_dir / "qa_summary.json").exists()
    assert not (out_dir / "qa_metrics.json").exists()


def _seed_stray_metrics(artifact_root: Path, doc_id: str, run_id: str) -> Path:
    """Seed a metrics file in the canonical qa_metrics dir that mtime-scan would find."""
    metrics = {
        "schema_version": "qa_metrics.v1",
        "document_id": doc_id,
        "run_id": run_id,
        "edition": "ru",
        "totals": {"info": 0, "warning": 0, "error": 0, "critical": 0},
    }
    path = artifact_root / doc_id / "qa_metrics.v1" / "document" / doc_id / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics))
    return path


def test_ref_bound_legacy_summary_skips_metrics_without_mtime_fallback(
    qa_module: ModuleType, tmp_path: Path
) -> None:
    """S5U-888: ref_bound + a legacy summary (no qa_metrics_ref) must NOT mtime-splice metrics.

    The bound summary predates S5U-641 and carries no ``qa_metrics_ref``. A
    stray metrics file produced by a *different* run sits in the global
    ``qa_metrics.v1`` directory with a newer mtime. In run-bound mode the
    legacy mtime directory scan is run-agnostic and would splice that foreign
    run's metrics into the bundle — the exact cross-run hazard S5U-869 closed
    for the other artifact classes. The export must skip metrics instead.
    """
    doc_id = "doc1"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id

    # Bound summary: legacy shape — no qa_metrics_ref field.
    bound = artifact_root / doc_id / "qa" / "document" / doc_id / "run_bound.json"
    bound.parent.mkdir(parents=True, exist_ok=True)
    bound.write_text(
        json.dumps(
            {
                "schema_version": "qa_summary.v1",
                "document_id": doc_id,
                "run_id": "run_bound",
                "edition": "ru",
                "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "blocking": False,
                "record_refs": [],
                "review_pack_ref": "",
            }
        )
    )

    # A stray metrics file from an unrelated newer run — mtime scan would pick it.
    _seed_stray_metrics(artifact_root, doc_id, "run_stray")

    count = qa_module.export_qa(
        artifact_root, doc_id, "ru", doc_public, summary_path=bound, ref_bound=True
    )

    assert count == 0
    # Summary itself is exported (it IS the bound run's summary)...
    assert (doc_public / "ru" / "data" / "qa_summary.json").exists()
    # ...but the foreign-run metrics file must NOT be spliced in.
    assert not (doc_public / "ru" / "data" / "qa_metrics.json").exists()


def test_ref_bound_legacy_summary_drops_stale_qa_metrics(
    qa_module: ModuleType, tmp_path: Path
) -> None:
    """S5U-888: ref_bound + legacy summary must drop a prior export's qa_metrics.json.

    Even when the mtime scan is refused, a leftover ``qa_metrics.json`` from a
    prior run's export must be removed so the reader does not splice run-A
    metrics over the bound run's QA bundle.
    """
    doc_id = "doc1"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    out_dir = doc_public / "ru" / "data"
    out_dir.mkdir(parents=True)
    (out_dir / "qa_metrics.json").write_text(json.dumps({"run_id": "run_a"}))

    bound = artifact_root / doc_id / "qa" / "document" / doc_id / "run_bound.json"
    bound.parent.mkdir(parents=True, exist_ok=True)
    bound.write_text(
        json.dumps(
            {
                "schema_version": "qa_summary.v1",
                "document_id": doc_id,
                "run_id": "run_bound",
                "edition": "ru",
                "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "blocking": False,
                "record_refs": [],
                "review_pack_ref": "",
            }
        )
    )
    _seed_stray_metrics(artifact_root, doc_id, "run_stray")

    qa_module.export_qa(artifact_root, doc_id, "ru", doc_public, summary_path=bound, ref_bound=True)

    assert (out_dir / "qa_summary.json").exists()
    assert not (out_dir / "qa_metrics.json").exists()


def test_ref_bound_explicit_summary_path_exported(qa_module: ModuleType, tmp_path: Path) -> None:
    """A supplied summary_path is exported verbatim under ref_bound mode."""
    doc_id = "doc1"
    artifact_root = tmp_path / "artifacts"
    doc_public = tmp_path / "public" / doc_id
    bound = artifact_root / doc_id / "qa" / "document" / doc_id / "bound.json"
    bound.parent.mkdir(parents=True, exist_ok=True)
    bound.write_text(
        json.dumps(
            {
                "schema_version": "qa_summary.v1",
                "document_id": doc_id,
                "run_id": "run_bound",
                "edition": "ru",
                "counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "waived_counts": {"info": 0, "warning": 0, "error": 0, "critical": 0},
                "blocking": False,
                "record_refs": [],
                "review_pack_ref": "",
            }
        )
    )

    count = qa_module.export_qa(
        artifact_root, doc_id, "ru", doc_public, summary_path=bound, ref_bound=True
    )

    assert count == 0
    exported = json.loads((doc_public / "ru" / "data" / "qa_summary.json").read_text())
    assert exported["document_id"] == doc_id
