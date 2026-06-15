"""Stage live ``images/`` writes behind the two-phase atomic swap (S5U-1223).

S5U-890 made the export build every edition into a staging dir and swap the live
bundle only after the whole bundle is proven. But ``extract_images`` still wrote
decoded PDF images straight into the live ``doc_public/images`` dir in phase 1.5
— *before* staging/validation. A phase-2 validation refusal (the exact scenario
S5U-890 exists for) therefore still mutated live ``images/``: a partial mutation
the contract says cannot happen.

These tests pin the fix:

* a phase-2 validation refusal leaves live ``images/`` byte-identical (extraction
  now writes into a staging dir that is discarded on refusal), AND
* a swap-time ``OSError`` rolls back ``images/`` along with the editions, AND
* a happy-path export swaps the extracted images live (the published URL — and
  the on-disk live location after the swap — is unchanged).

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
)


def _extract_into_target(*args: object, **kwargs: object) -> dict[str, list[dict]]:
    """Stand-in for ``extract_images`` that writes one image into its target dir.

    The real ``extract_images`` decodes PDF images and writes them under the
    directory it is handed. This stub mirrors that single observable side-effect
    (a written PNG) so the staging assertions exercise the on-disk write path
    without needing a real PDF. It honours the staged-dir argument the fix passes
    in (positional ``target_dir`` or keyword); pre-fix the production call writes
    into live ``doc_public/images`` and ignores any target, so this stub's write
    lands live and the refusal test fails (red-before).
    """
    target = kwargs.get("target_dir")
    if target is None and len(args) >= 3:
        target = args[2]  # extract_images(doc_id, doc_public, target_dir, ...)
    assert isinstance(target, Path)
    target.mkdir(parents=True, exist_ok=True)
    (target / "extracted.png").write_bytes(b"NEW-IMAGE-BYTES")
    return {
        "p0001": [
            {
                "asset_id": "p0001.extracted",
                "src": "/documents/doc1/images/extracted.png",
                "alt": "p0001.extracted",
                "width": 120,
                "height": 120,
            }
        ]
    }


def test_phase2_refusal_leaves_live_images_untouched(
    export_module: ModuleType,  # noqa: F811 — pytest fixture injection
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A phase-2 validation refusal leaves the live ``images/`` dir byte-identical.

    Seeds a single run whose render page fails post-build validation (mismatched
    internal ``page.id``) and a pre-existing live ``images/sentinel.png`` from a
    prior export. Image extraction (stubbed to write a new PNG into whatever
    target dir it is given) must write into a *staging* dir that the refusal
    discards — so live ``images/`` still holds only the sentinel, with no
    ``extracted.png``.

    Pre-fix, ``extract_images`` wrote into live ``doc_public/images`` directly, so
    the new PNG landed live in phase 1.5 and survived the phase-2 refusal — the
    partial mutation this test forbids.
    """
    monkeypatch.setattr(export_module, "extract_images", _extract_into_target)

    documents_root = documents_root_for(tmp_path)
    # A pre-existing live images/ dir (left by a prior good export).
    live_images = documents_root / "doc1" / "images"
    live_images.mkdir(parents=True, exist_ok=True)
    (live_images / "sentinel.png").write_bytes(b"OLD-SENTINEL")
    before = {p.name: p.read_bytes() for p in live_images.iterdir() if p.is_file()}

    # The only seeded run fails post-build validation (mismatched internal page.id).
    conn = init_registry(tmp_path / "registry.db")
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
        export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_b"])
    assert exc.value.code == 1
    after = {p.name: p.read_bytes() for p in live_images.iterdir() if p.is_file()}
    assert after == before  # only the sentinel; the refused run's image stayed staged
    assert "extracted.png" not in after
    assert no_swap_litter(documents_root)


def test_swap_failure_rolls_back_images(
    export_module: ModuleType,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A swap-time OSError restores the prior live ``images/`` along with editions.

    Establishes a prior live ``images/`` dir holding a ``sentinel.png`` that the
    incoming run's staged images do NOT contain, then re-exports with the
    *edition* swap failing *after* the images swap. The rollback must restore the
    prior live ``images/`` from its backup — so the sentinel reappears, proving
    the images dir was rolled back rather than left in the half-swapped
    (sentinel-less) staged state.
    """
    monkeypatch.setattr(export_module, "extract_images", _extract_into_target)

    documents_root = documents_root_for(tmp_path)
    # Prior good live images/ dir; the sentinel is absent from the staged set the
    # incoming run extracts, so its survival is the rollback witness.
    live_images = documents_root / "doc1" / "images"
    live_images.mkdir(parents=True, exist_ok=True)
    (live_images / "sentinel.png").write_bytes(b"OLD-SENTINEL")

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

    # Fail the *edition* swap (the images swap, ordered first, succeeds), forcing
    # the rollback path to restore images/ from its backup.
    commit_mod = sys.modules["_export_commit"]
    real_swap_dir = commit_mod._swap_dir

    def _flaky(staged: Path, live: Path, backup: Path) -> None:
        if live.name == "en":
            raise OSError("simulated edition swap failure")
        real_swap_dir(staged, live, backup)

    monkeypatch.setattr(commit_mod, "_swap_dir", _flaky)

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    assert exc.value.code == 1
    # images/ rolled back: the sentinel (absent from the failed run's staged set)
    # is restored, and the half-swapped extracted.png is gone.
    names = {p.name for p in live_images.iterdir() if p.is_file()}
    assert names == {"sentinel.png"}
    assert (live_images / "sentinel.png").read_bytes() == b"OLD-SENTINEL"
    assert no_swap_litter(documents_root)


def test_happy_path_swaps_extracted_images_live(
    export_module: ModuleType,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A successful export swaps the extracted images into the live ``images/`` dir.

    Pins that staging does not drop the images on the floor: after a clean export
    the live ``doc_public/images`` holds the extracted PNG (the published
    ``/documents/doc1/images/...`` URL still resolves on disk).
    """
    monkeypatch.setattr(export_module, "extract_images", _extract_into_target)

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
    live_images = documents_root / "doc1" / "images"
    assert (live_images / "extracted.png").read_bytes() == b"NEW-IMAGE-BYTES"
    assert no_swap_litter(documents_root)
