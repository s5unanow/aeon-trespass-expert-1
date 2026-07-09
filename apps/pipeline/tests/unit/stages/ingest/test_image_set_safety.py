"""Path safety and refusal contract tests for image-set ingest (S5U-1535).

Every "Must refuse" case must:
- Raise before any artifact write.
- Leave the provided ArtifactStore untouched.
- Have clear error messaging.

Three-input style per case where applicable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.ingest.image_set import (
    register_image_set,
    resolve_safe_path,
)
from atr_pipeline.store.artifact_store import ArtifactStore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_iset_ctx(tmp_path: Path, manifest_path: Path) -> StageContext:
    """Build a ctx whose document points at the given (possibly evil) manifest."""
    config = load_document_config("image_set_tiny", repo_root=_repo_root())
    # Force the image_set source to the test manifest path (absolute string)
    config.document.source_kind = "image_set"
    config.document.source_image_set = str(manifest_path)
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "reg.db")
    start_run(
        conn,
        run_id="safety",
        document_id="image_set_tiny",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="safety",
        document_id="image_set_tiny",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def test_resolve_safe_path_rejects_null_byte(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="null byte"):
        resolve_safe_path(candidate="foo\x00bar.png", repo_root=_repo_root())


def test_resolve_safe_path_rejects_dotdot_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.\."):
        resolve_safe_path(candidate="../outside.png", repo_root=_repo_root())


def test_image_set_ingest_refuses_traversal_manifest(tmp_path: Path) -> None:
    """Manifest path with .. must be refused before any write."""
    evil_manifest = tmp_path / "evil_manifest.json"
    evil_manifest.write_text(
        json.dumps(
            {
                "schema_version": "image_set_manifest.v1",
                "images": [{"page_id": "p0001", "path": "../evil.png"}],
            }
        )
    )
    store = ArtifactStore(tmp_path / "art")
    before = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []

    with pytest.raises(ValueError):
        register_image_set(
            document_id="t",
            manifest_path=evil_manifest,
            repo_root=_repo_root(),
            store=store,
        )

    after = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    assert before == after, "artifact store must be untouched on refusal"


def test_image_set_ingest_refuses_absolute_escape(tmp_path: Path) -> None:
    """Absolute path outside allowed roots is refused with no writes."""
    evil = tmp_path / "abs_manifest.json"
    evil.write_text(
        json.dumps(
            {
                "schema_version": "image_set_manifest.v1",
                "images": [{"page_id": "p0001", "path": "/etc/passwd"}],
            }
        )
    )
    store = ArtifactStore(tmp_path / "art")
    before = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []

    with pytest.raises(ValueError):
        register_image_set(
            document_id="t",
            manifest_path=evil,
            repo_root=_repo_root(),
            store=store,
        )

    after = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    assert before == after


def test_image_set_ingest_refuses_null_byte_in_image_path(tmp_path: Path) -> None:
    m = tmp_path / "nullimg.json"
    m.write_text(
        json.dumps(
            {
                "schema_version": "image_set_manifest.v1",
                "images": [{"page_id": "p0001", "path": "p00\x001.png"}],
            }
        )
    )
    store = ArtifactStore(tmp_path / "art")
    before = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    with pytest.raises(ValueError):
        register_image_set(document_id="t", manifest_path=m, repo_root=_repo_root(), store=store)
    after = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    assert before == after


def test_image_set_ingest_refuses_unsupported_media_type(tmp_path: Path) -> None:
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"not an image")
    m = tmp_path / "badmedia.json"
    m.write_text(
        json.dumps(
            {
                "schema_version": "image_set_manifest.v1",
                "images": [{"page_id": "p0001", "path": str(bad)}],
            }
        )
    )
    store = ArtifactStore(tmp_path / "art")
    before = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    with pytest.raises(ValueError, match=r"Unsupported|media"):
        register_image_set(document_id="t", manifest_path=m, repo_root=_repo_root(), store=store)
    after = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    assert before == after


def test_image_set_ingest_refuses_duplicate_image_id(tmp_path: Path) -> None:
    # Place manifest *under repo root* (tmp/safety-...) so manifest resolution itself passes.
    safe_dir = _repo_root() / "tmp" / "safety" / "dups"
    safe_dir.mkdir(parents=True, exist_ok=True)
    real_img = _repo_root() / "packages/fixtures/image_sets/image_set_tiny/source/p0001.png"
    m = safe_dir / "dups.json"
    m.write_text(
        json.dumps(
            {
                "schema_version": "image_set_manifest.v1",
                "images": [
                    {"page_id": "p0001", "path": str(real_img)},
                    {"page_id": "p0001", "path": str(real_img)},
                ],
            }
        )
    )
    store = ArtifactStore(tmp_path / "art")
    before = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    with pytest.raises(ValueError, match="Duplicate"):
        register_image_set(document_id="t", manifest_path=m, repo_root=_repo_root(), store=store)
    after = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    assert before == after
    # cleanup
    m.unlink(missing_ok=True)


def test_image_set_ingest_refuses_missing_image(tmp_path: Path) -> None:
    safe_dir = _repo_root() / "tmp" / "safety" / "missing"
    safe_dir.mkdir(parents=True, exist_ok=True)
    m = safe_dir / "missingimg.json"
    m.write_text(
        json.dumps(
            {
                "schema_version": "image_set_manifest.v1",
                "images": [{"page_id": "p0001", "path": "no_such.png"}],
            }
        )
    )
    store = ArtifactStore(tmp_path / "art")
    before = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    with pytest.raises(FileNotFoundError):
        register_image_set(document_id="t", manifest_path=m, repo_root=_repo_root(), store=store)
    after = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    assert before == after
    m.unlink(missing_ok=True)


def test_image_set_ingest_refuses_malformed_manifest(tmp_path: Path) -> None:
    safe_dir = _repo_root() / "tmp" / "safety" / "malformed"
    safe_dir.mkdir(parents=True, exist_ok=True)
    m = safe_dir / "badjson.json"
    m.write_text("{ not json ")
    store = ArtifactStore(tmp_path / "art")
    before = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    with pytest.raises(ValueError, match=r"Malformed|JSON|decode"):
        register_image_set(document_id="t", manifest_path=m, repo_root=_repo_root(), store=store)
    after = list((tmp_path / "art").rglob("*")) if (tmp_path / "art").exists() else []
    assert before == after
    m.unlink(missing_ok=True)
