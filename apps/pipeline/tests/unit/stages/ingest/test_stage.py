"""Tests for the ingest stage."""

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import StageScope
from atr_schemas.source_manifest_v1 import SourceManifestV1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path) -> StageContext:
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="test_run",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="test_run",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def test_ingest_implements_stage_protocol() -> None:
    """IngestStage satisfies the Stage protocol."""
    stage = IngestStage()
    assert isinstance(stage, Stage)
    assert stage.name == "ingest"
    assert stage.scope == StageScope.DOCUMENT
    assert stage.version == "1.0"


def test_ingest_produces_manifest(tmp_path: Path) -> None:
    """Ingest stage produces a valid SourceManifestV1 artifact."""
    ctx = _make_ctx(tmp_path)
    result = execute_stage(IngestStage(), ctx)

    assert result.success
    assert result.artifact_ref is not None

    data = ctx.artifact_store.get_json(result.artifact_ref)
    manifest = SourceManifestV1.model_validate(data)
    assert manifest.document_id == "walking_skeleton"
    assert manifest.page_count == 1
    assert manifest.pages[0].page_id == "p0001"
    assert len(manifest.source_pdf_sha256) == 64


def test_ingest_produces_raster(tmp_path: Path) -> None:
    """Ingest stage produces page rasters for each pyramid DPI level."""
    ctx = _make_ctx(tmp_path)
    execute_stage(IngestStage(), ctx)

    # Check raster pyramid levels exist in artifact store (default: 150, 300 DPI)
    raster_base = tmp_path / "artifacts" / "walking_skeleton" / "raster" / "page"
    pyramid_dirs = sorted(d.name for d in raster_base.iterdir() if d.is_dir())
    assert "p0001__150dpi" in pyramid_dirs
    assert "p0001__300dpi" in pyramid_dirs

    # Each level has a PNG
    for dpi_dir in pyramid_dirs:
        rasters = list((raster_base / dpi_dir).glob("*.png"))
        assert len(rasters) == 1
        assert rasters[0].stat().st_size > 100  # Not empty

    # Check raster metadata JSON was stored
    meta_dir = tmp_path / "artifacts" / "walking_skeleton" / "raster_meta.v1" / "page" / "p0001"
    assert meta_dir.exists()
    jsons = list(meta_dir.glob("*.json"))
    assert len(jsons) == 1


def test_ingest_cache_hit(tmp_path: Path) -> None:
    """Running ingest twice hits cache on second run."""
    ctx = _make_ctx(tmp_path)
    r1 = execute_stage(IngestStage(), ctx, input_hashes=["fixed"])
    r2 = execute_stage(IngestStage(), ctx, input_hashes=["fixed"])

    assert r1.success and not r1.cached
    assert r2.success and r2.cached
