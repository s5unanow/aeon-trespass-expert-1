"""Tests for the ingest stage."""

from pathlib import Path

import pytest

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
    assert stage.version == "1.2"  # S5U-1221: PDF content hash folded into cache key


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


# --- S5U-1535 source abstraction regression + image-set tests ---


def test_document_config_legacy_source_pdf_normalizes_to_pdf_variant() -> None:
    """Legacy document.source_pdf (no source_kind) produces PDF variant.

    AC requirement: existing configs load to the PDF source with identical
    fingerprint/cache behavior. This test asserts the normalization.
    """
    from atr_pipeline.config.models import DocumentConfig

    # Simulate what the TOML loader produces for classic docs
    cfg = DocumentConfig(
        id="legacy_pdf",
        source_pdf="packages/fixtures/sample_documents/walking_skeleton/source/sample_page_01.pdf",
    )
    assert cfg.source_kind == "pdf"
    assert cfg.source_pdf  # non-empty
    # source_image_set remains default empty
    assert cfg.source_image_set == ""


def test_document_config_unknown_source_kind_rejected() -> None:
    """Unknown source_kind fails closed at model construction (Literal)."""
    from pydantic import ValidationError

    from atr_pipeline.config.models import DocumentConfig

    with pytest.raises(ValidationError):
        DocumentConfig(id="bad", source_kind="foo", source_pdf="x")  # type: ignore[arg-type]


def test_image_set_ingest_via_executor_emits_manifest_and_raw_artifact(tmp_path: Path) -> None:
    """Image-set config + manifest produces SourceManifestV1 + registered raw image.

    Determinism: two runs on identical inputs produce byte-identical manifest JSON.
    """
    from atr_pipeline.config import load_document_config
    from atr_pipeline.registry.db import open_registry
    from atr_pipeline.registry.runs import start_run
    from atr_pipeline.store.artifact_store import ArtifactStore

    repo = _repo_root()
    # Load the committed image_set_tiny config
    config = load_document_config("image_set_tiny", repo_root=repo)
    # Override artifact root to tmp to keep test hermetic
    config.artifact_root = tmp_path / "artifacts"

    store = ArtifactStore(config.artifact_root)
    conn = open_registry(tmp_path / "reg.db")
    start_run(
        conn,
        run_id="iset1",
        document_id="image_set_tiny",
        pipeline_version="0.1.0",
        config_hash="",
    )

    ctx = StageContext(
        run_id="iset1",
        document_id="image_set_tiny",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=repo,
    )

    r1 = execute_stage(IngestStage(), ctx)
    assert r1.success
    data1 = store.get_json(r1.artifact_ref) if r1.artifact_ref else {}
    m1 = SourceManifestV1.model_validate(data1)
    assert m1.document_id == "image_set_tiny"
    assert m1.page_count == 1
    assert m1.pages[0].page_id == "p0001"
    assert m1.source_pdf_sha256 == ""
    assert m1.source_image_set_sha256  # populated
    assert len(m1.image_entries) == 1

    # Raw image registered
    raw_dir = tmp_path / "artifacts" / "image_set_tiny" / "source_image" / "page" / "p0001"
    assert raw_dir.exists()
    files = list(raw_dir.glob("*"))
    assert len(files) == 1
    assert files[0].stat().st_size > 0

    # Second run (new ctx/store but same inputs) -> identical manifest JSON
    store2 = ArtifactStore(config.artifact_root)
    conn2 = open_registry(tmp_path / "reg2.db")
    start_run(
        conn2,
        run_id="iset2",
        document_id="image_set_tiny",
        pipeline_version="0.1.0",
        config_hash="",
    )
    ctx2 = StageContext(
        run_id="iset2",
        document_id="image_set_tiny",
        config=config,
        artifact_store=store2,
        registry_conn=conn2,
        repo_root=repo,
    )
    r2 = execute_stage(IngestStage(), ctx2)
    data2 = store2.get_json(r2.artifact_ref) if r2.artifact_ref else {}
    m2 = SourceManifestV1.model_validate(data2)
    assert m1.model_dump_json() == m2.model_dump_json()

    conn.close()
    conn2.close()
