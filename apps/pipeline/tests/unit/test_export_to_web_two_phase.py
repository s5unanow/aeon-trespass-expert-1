"""Fail-closed two-phase-commit integrity for `make export` (S5U-890), part 1.

S5U-869 made the export ref-bound, but the writer still mutated the live web
bundle edition-by-edition *before* proving the whole bundle exportable. Three
late-failure paths left a partial or cross-edition bundle on disk after a
non-zero exit: a missing glossary file, a post-write validation failure, and the
EN-before-RU split in ``--edition all``. These tests drive
``export_to_web.main()`` against a registry + artifact-store fixture and assert,
for each degenerate input (guards.md Rule G1), that:

* the export refuses (``SystemExit(1)``), AND
* **the on-disk bundle is byte-identical to the prior good bundle** — no partial
  EN, no cross-edition split, prior run's bundle fully intact.

Part 2 (``test_export_to_web_two_phase_regress.py``) covers the regression pins
(QA-summary / raster missing) and the happy-path all-edition swap. Shared
fixture + seed helpers live in ``_two_phase_export_helpers``.
"""

from __future__ import annotations

import json
import sqlite3
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


def test_glossary_missing_file_leaves_prior_bundle_intact(
    export_module: ModuleType,  # noqa: F811 — pytest fixture injection
    tmp_path: Path,
) -> None:
    """G1-a: a missing glossary ref file refuses with the prior bundle untouched.

    Pre-fix, ``resolve_glossary_path`` ran *after* rasters/pages/manifest were
    written, so run B's pages + manifest were already live when the glossary
    raise fired. The two-phase commit resolves the glossary in phase 1, before
    any write.
    """
    conn = init_registry(tmp_path / "registry.db")
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="commit_a",
        page_text="GOOD-A",
        with_glossary=True,
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)

    export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    good = snapshot(documents_root)
    assert good  # run A is live

    # Run B advertises a glossary whose artifact file does NOT exist on disk.
    conn = sqlite3.connect(str(tmp_path / "registry.db"))
    conn.row_factory = sqlite3.Row
    gref = seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_b",
        started_at="2026-02-01T00:00:00",
        edition="en",
        git_commit="commit_b",
        page_text="PARTIAL-B",
        with_glossary=True,
    )
    conn.close()
    (export_module.ARTIFACT_ROOT / gref).unlink()  # delete the glossary file

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    # Integrity: live bundle is byte-identical to run A — no run-B pages/manifest.
    assert snapshot(documents_root) == good
    assert no_swap_litter(documents_root)


def test_post_write_validation_failure_leaves_prior_bundle_intact(
    export_module: ModuleType,  # noqa: F811
    tmp_path: Path,
) -> None:
    """G1-b: a post-build validation failure refuses with the prior bundle untouched.

    Pre-fix, ``run_export_validation`` ran against the already-written live
    edition dir, so a failure left the bad bundle live. The staged build runs
    validation against the staging dir and aborts before any swap.
    """
    conn = init_registry(tmp_path / "registry.db")
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="commit_a",
        page_text="GOOD-A",
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)

    export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    good = snapshot(documents_root)
    assert good

    # Run B's render page has a mismatched internal page.id → validation fails.
    conn = sqlite3.connect(str(tmp_path / "registry.db"))
    conn.row_factory = sqlite3.Row
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_b",
        started_at="2026-02-01T00:00:00",
        edition="en",
        git_commit="commit_b",
        page_text="BAD-B",
        bad_internal_id=True,
    )
    conn.close()

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    assert snapshot(documents_root) == good
    assert no_swap_litter(documents_root)


def test_en_resolves_but_ru_fails_no_cross_edition_split(
    export_module: ModuleType,  # noqa: F811
    tmp_path: Path,
) -> None:
    """G1-c: in ``--edition all`` an RU-side failure must not leave a written EN bundle.

    Pre-fix, the EN iteration fully wrote ``.../en/`` before the RU iteration
    resolved, so an RU refusal left EN=run B next to RU=run A — a cross-edition
    splice. Phase 1 resolves BOTH editions before building either, so the RU
    failure refuses with neither edition advanced.
    """
    conn = init_registry(tmp_path / "registry.db")
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="en_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="en_commit_a",
        page_text="EN-GOOD-A",
    )
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="ru_a",
        started_at="2026-01-02T00:00:00",
        edition="ru",
        git_commit="ru_commit_a",
        page_text="RU-GOOD-A",
    )
    conn.close()
    documents_root = documents_root_for(tmp_path)

    # Establish a good EN+RU bundle (both editions from run *_a).
    export_module.main(["--doc", "doc1", "--edition", "all"])
    good = snapshot(documents_root)
    assert any(k.startswith("en/") for k in good)
    assert any(k.startswith("ru/") for k in good)

    # Newer EN run B resolves fine; newer RU run B advertises a glossary whose
    # file is missing → RU phase-1 resolution raises.
    conn = sqlite3.connect(str(tmp_path / "registry.db"))
    conn.row_factory = sqlite3.Row
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="en_b",
        started_at="2026-02-01T00:00:00",
        edition="en",
        git_commit="en_commit_b",
        page_text="EN-NEW-B",
    )
    gref = seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="ru_b",
        started_at="2026-02-02T00:00:00",
        edition="ru",
        git_commit="ru_commit_b",
        page_text="RU-NEW-B",
        with_glossary=True,
    )
    conn.close()
    (export_module.ARTIFACT_ROOT / gref).unlink()

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "all"])
    assert exc.value.code == 1
    # Integrity: BOTH editions are still run *_a — EN was NOT advanced to run B.
    after = snapshot(documents_root)
    assert after == good
    en_manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert en_manifest["provenance"]["run_id"] == "en_a"
    assert no_swap_litter(documents_root)
