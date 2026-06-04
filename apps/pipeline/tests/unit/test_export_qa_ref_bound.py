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
