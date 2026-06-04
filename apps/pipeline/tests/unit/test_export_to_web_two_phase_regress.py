"""Fail-closed two-phase-commit export (S5U-890), part 2: regressions + happy path.

Companion to ``test_export_to_web_two_phase.py``. Covers the two surfaces the
issue confirmed were *already* fail-closed before any write (QA-summary missing,
page-ref missing — regression pins so the refactor doesn't reopen them), the
raster-missing fail-closed path, and the happy-path all-edition atomic swap
(which must preserve the S5U-892 stale-companion cleanup invariant). Shared
fixture + seed helpers live in ``_two_phase_export_helpers``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import ModuleType

import pytest

from ._export_run_fixtures import add_run, init_registry, write_render_result
from ._two_phase_export_helpers import (
    documents_root_for,
    export_module,  # noqa: F401 — pytest fixture re-exported for collection
    no_swap_litter,
    seed_facsimile_run,
    seed_run,
    snapshot,
)


def test_missing_qa_summary_still_refuses_pre_write(
    export_module: ModuleType,  # noqa: F811 — pytest fixture injection
    tmp_path: Path,
) -> None:
    """G1-d regression: a run with no resolvable QA summary still fails closed.

    Already pre-validated by the S5U-870 gate before any write; this pins that
    the two-phase refactor did not regress it.
    """
    conn = init_registry(tmp_path / "registry.db")
    render_ref = "doc1/render/document/doc1/run_x.json"
    page_ref = "doc1/render_page.v1/page/p0001/run_x.json"
    ppath = export_module.ARTIFACT_ROOT / page_ref
    ppath.parent.mkdir(parents=True, exist_ok=True)
    ppath.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "page": {"id": "p0001", "page_id": "p0001", "title": "P"},
                "blocks": [
                    {
                        "kind": "paragraph",
                        "id": "p0001.b0",
                        "children": [{"kind": "text", "text": "x"}],
                    }
                ],
            }
        )
    )
    write_render_result(export_module.ARTIFACT_ROOT, render_ref, {"page_refs": {"p0001": page_ref}})
    qa_ref = "doc1/qa/document/doc1/run_x.json"
    qpath = export_module.ARTIFACT_ROOT / qa_ref
    qpath.parent.mkdir(parents=True, exist_ok=True)
    qpath.write_text(
        json.dumps(
            {
                "schema_version": "qa_summary.v1",
                "document_id": "doc1",
                "run_id": "run_x",
                "edition": "en",
                "blocking": False,
                "record_refs": [],
                "review_pack_ref": "",
            }
        )
    )
    add_run(
        conn,
        run_id="run_x",
        started_at="2026-01-01T00:00:00",
        edition="en",
        render_ref=render_ref,
        qa_summary_ref=qa_ref,
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)
    qpath.unlink()  # QA summary file now missing → gate refuses pre-write

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    # No bundle was ever written for doc1.
    assert snapshot(documents_root) == {}
    assert no_swap_litter(documents_root)


def test_missing_raster_file_leaves_prior_bundle_intact(
    export_module: ModuleType,  # noqa: F811
    tmp_path: Path,
) -> None:
    """G1-f: a facsimile run whose raster file is missing refuses, prior rasters intact.

    The raster copy now targets a staging dir (S5U-890) so a missing raster ref
    raises before the live ``rasters/`` dir is swapped.
    """
    conn = init_registry(tmp_path / "registry.db")
    seed_facsimile_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        raster_bytes=b"GOOD-RASTER-A",
        write_raster=True,
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)

    export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    good = snapshot(documents_root)
    rasters_dir = documents_root / "doc1" / "rasters"
    assert (rasters_dir / "p0007__150dpi.png").read_bytes() == b"GOOD-RASTER-A"

    # Run B records a raster ref whose PNG is absent on disk.
    conn = sqlite3.connect(str(tmp_path / "registry.db"))
    conn.row_factory = sqlite3.Row
    seed_facsimile_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_b",
        started_at="2026-02-01T00:00:00",
        raster_bytes=b"unused",
        write_raster=False,
    )
    conn.close()

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    # Integrity: the prior good raster + bundle are untouched.
    assert (rasters_dir / "p0007__150dpi.png").read_bytes() == b"GOOD-RASTER-A"
    assert snapshot(documents_root) == good
    assert no_swap_litter(documents_root)


def test_successful_all_edition_export_swaps_both_and_cleans_companions(
    export_module: ModuleType,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Happy path: ``--edition all`` swaps both editions atomically; stale companions gone.

    Confirms the two-phase commit does not regress the S5U-892 stale-companion
    invariant: a re-export to a run that lacks a glossary leaves no leftover
    ``glossary.json`` (the whole edition dir is replaced via the atomic swap).
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
        with_glossary=True,
    )
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="ru_a",
        started_at="2026-01-02T00:00:00",
        edition="ru",
        git_commit="ru_a",
        page_text="RU-A",
        with_glossary=True,
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)

    export_module.main(["--doc", "doc1", "--edition", "all"])
    en_data = documents_root / "doc1" / "en" / "data"
    ru_data = documents_root / "doc1" / "ru" / "data"
    assert (en_data / "glossary.json").exists()
    assert (ru_data / "glossary.json").exists()

    # Newer runs for both editions, neither carrying a glossary.
    conn = sqlite3.connect(str(tmp_path / "registry.db"))
    conn.row_factory = sqlite3.Row
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="en_b",
        started_at="2026-02-01T00:00:00",
        edition="en",
        git_commit="en_b",
        page_text="EN-B",
        with_glossary=False,
    )
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="ru_b",
        started_at="2026-02-02T00:00:00",
        edition="ru",
        git_commit="ru_b",
        page_text="RU-B",
        with_glossary=False,
    )
    conn.close()

    export_module.main(["--doc", "doc1", "--edition", "all"])
    # Both editions advanced to run *_b and the stale glossaries are gone.
    en_manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    ru_manifest = json.loads((documents_root / "doc1" / "ru" / "manifest.json").read_text())
    assert en_manifest["provenance"]["run_id"] == "en_b"
    assert ru_manifest["provenance"]["run_id"] == "ru_b"
    assert not (en_data / "glossary.json").exists()
    assert not (ru_data / "glossary.json").exists()
    assert no_swap_litter(documents_root)
