"""Tests for ``ResolvedRun.raster_refs`` — run-bound facsimile rasters (S5U-891).

The render result carries ``raster_refs`` as ``{page_id: {dpi: rel_path}}`` (see
``stages/render/stage.py``). S5U-869 bound pages/glossary/QA to a single resolved
run but left the facsimile raster PNGs selected globally; this accessor surfaces
the run's own raster refs so the exporter can bind them. Lives in its own file to
keep ``test_export_run.py`` under the 400-line cap.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ._export_run_fixtures import add_run, init_registry, write_render_result

REPO = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO / "scripts"
RUN_MODULE_PATH = SCRIPTS_DIR / "_export_run.py"


@pytest.fixture()
def run_module() -> Iterator[ModuleType]:
    """Import _export_run.py as a module, cleaning up sys.modules after."""
    sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("_export_run", RUN_MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_run"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_run", None)


@pytest.fixture()
def repo(tmp_path: Path) -> tuple[Path, Path]:
    """Return (registry_path, artifact_root)."""
    return tmp_path / "registry.db", tmp_path / "artifacts"


def _resolve(repo: tuple[Path, Path], run_module: ModuleType, render_payload: dict) -> object:
    registry_path, artifact_root = repo
    conn = init_registry(registry_path)
    ref = "doc1/render/document/doc1/a.json"
    add_run(conn, run_id="run_a", started_at="2026-01-01T00:00:00", render_ref=ref)
    conn.close()
    write_render_result(artifact_root, ref, render_payload)
    return run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)


def test_raster_refs_parsed_with_int_dpi_keys(
    repo: tuple[Path, Path], run_module: ModuleType
) -> None:
    """JSON object keys are strings; the accessor coerces dpi back to int."""
    resolved = _resolve(
        repo,
        run_module,
        {
            "page_refs": {"p0007": "x.json"},
            # Persisted JSON has string dpi keys.
            "raster_refs": {
                "p0007": {
                    "150": "doc1/raster.v1/page/p0007/150.png",
                    "300": "doc1/raster.v1/page/p0007/300.png",
                }
            },
        },
    )
    assert resolved.raster_refs == {
        "p0007": {
            150: "doc1/raster.v1/page/p0007/150.png",
            300: "doc1/raster.v1/page/p0007/300.png",
        }
    }


def test_raster_refs_empty_when_absent(repo: tuple[Path, Path], run_module: ModuleType) -> None:
    """A run with no facsimile rasters yields an empty mapping (not an error)."""
    resolved = _resolve(repo, run_module, {"page_refs": {"p0001": "x.json"}})
    assert resolved.raster_refs == {}


def test_raster_refs_drops_malformed_entries(
    repo: tuple[Path, Path], run_module: ModuleType
) -> None:
    """Non-dict inner / non-int dpi entries are dropped, not raised, by the accessor."""
    resolved = _resolve(
        repo,
        run_module,
        {
            "page_refs": {"p0001": "x.json"},
            "raster_refs": {
                "p0001": "not-a-dict",
                "p0002": {"notanint": "ref.png", "150": "good.png"},
            },
        },
    )
    # p0001 dropped entirely (inner not a dict); p0002 keeps only the int dpi.
    assert resolved.raster_refs == {"p0002": {150: "good.png"}}


def test_raster_refs_cross_run_isolation(repo: tuple[Path, Path], run_module: ModuleType) -> None:
    """Resolving run A's raster_refs never surfaces run B's raster refs (splice guard)."""
    registry_path, artifact_root = repo
    conn = init_registry(registry_path)
    ref_a = "doc1/render/document/doc1/a.json"
    ref_b = "doc1/render/document/doc1/b.json"
    add_run(conn, run_id="run_a", started_at="2026-01-01T00:00:00", render_ref=ref_a)
    add_run(conn, run_id="run_b", started_at="2026-02-01T00:00:00", render_ref=ref_b)
    conn.close()
    write_render_result(
        artifact_root,
        ref_a,
        {"page_refs": {"p0007": "x.json"}, "raster_refs": {"p0007": {"150": "A/p0007.png"}}},
    )
    write_render_result(
        artifact_root,
        ref_b,
        {"page_refs": {"p0007": "x.json"}, "raster_refs": {"p0007": {"150": "B/p0007.png"}}},
    )

    resolved_a = run_module.resolve_run(
        registry_path, "doc1", artifact_root=artifact_root, run_id="run_a"
    )
    assert resolved_a.raster_refs == {"p0007": {150: "A/p0007.png"}}
    assert all("B/" not in r for levels in resolved_a.raster_refs.values() for r in levels.values())
