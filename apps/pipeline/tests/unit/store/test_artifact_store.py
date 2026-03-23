"""Tests for the immutable artifact store."""

import os
import time
from pathlib import Path

from atr_pipeline.store.artifact_store import ArtifactStore


def test_put_and_get_json(tmp_path: Path) -> None:
    """Write a JSON artifact and read it back."""
    store = ArtifactStore(tmp_path / "artifacts")
    data = {"schema_version": "test.v1", "value": 42}

    ref = store.put_json(
        document_id="test_doc",
        schema_family="test.v1",
        scope="page",
        entity_id="p0001",
        data=data,
    )

    assert store.has(ref)
    loaded = store.get_json(ref)
    assert loaded == data


def test_duplicate_write_returns_same_ref(tmp_path: Path) -> None:
    """Writing identical content twice returns the same ref without error."""
    store = ArtifactStore(tmp_path / "artifacts")
    data = {"hello": "world"}

    ref1 = store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data=data
    )
    ref2 = store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data=data
    )

    assert ref1 == ref2


def test_different_content_different_hash(tmp_path: Path) -> None:
    """Different content produces different content hashes."""
    store = ArtifactStore(tmp_path / "artifacts")

    ref1 = store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data={"a": 1}
    )
    ref2 = store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data={"a": 2}
    )

    assert ref1.content_hash != ref2.content_hash
    assert store.has(ref1)
    assert store.has(ref2)


def test_put_pydantic_model(tmp_path: Path) -> None:
    """Pydantic model can be stored directly."""
    from atr_schemas import QASummaryV1

    store = ArtifactStore(tmp_path / "artifacts")
    summary = QASummaryV1(document_id="test_doc", run_id="run_001")

    ref = store.put_json(
        document_id="test_doc",
        schema_family="qa_summary.v1",
        scope="document",
        entity_id="test_doc",
        data=summary,
    )

    loaded = store.get_json(ref)
    restored = QASummaryV1.model_validate(loaded)
    assert restored.document_id == "test_doc"


def test_missing_artifact_raises(tmp_path: Path) -> None:
    """Accessing a non-existent artifact raises FileNotFoundError."""
    from atr_pipeline.store.artifact_ref import ArtifactRef

    store = ArtifactStore(tmp_path / "artifacts")
    ref = ArtifactRef(
        schema_family="s.v1",
        scope="page",
        entity_id="p9999",
        content_hash="nonexistent",
        document_id="doc",
    )

    assert not store.has(ref)
    import pytest

    with pytest.raises(FileNotFoundError):
        store.get_json(ref)


def test_artifact_path_convention(tmp_path: Path) -> None:
    """Artifact path follows {doc}/{family}/{scope}/{id}/{hash}.json."""
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_json(
        document_id="my_doc",
        schema_family="page_ir.v1",
        scope="page",
        entity_id="p0042",
        data={"test": True},
    )

    path = store.get_path(ref)
    assert "my_doc/page_ir.v1/page/p0042/" in str(path)
    assert path.suffix == ".json"
    assert path.exists()


def test_put_bytes(tmp_path: Path) -> None:
    """Binary artifact write works."""
    store = ArtifactStore(tmp_path / "artifacts")
    data = b"\x89PNG fake image data"

    path = store.put_bytes(
        document_id="doc",
        schema_family="raster",
        scope="page",
        entity_id="p0001",
        data=data,
        extension=".png",
    )

    assert path.exists()
    assert path.read_bytes() == data


# ---- Deterministic artifact resolution tests (S5U-370) ----


def test_load_latest_json_returns_none_when_missing(tmp_path: Path) -> None:
    """load_latest_json returns None if no artifact exists."""
    store = ArtifactStore(tmp_path / "artifacts")
    result = store.load_latest_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001"
    )
    assert result is None


def test_load_latest_json_single_artifact(tmp_path: Path) -> None:
    """load_latest_json returns the single artifact when only one exists."""
    store = ArtifactStore(tmp_path / "artifacts")
    data = {"key": "value"}
    store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data=data
    )

    loaded = store.load_latest_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001"
    )
    assert loaded == data


def test_load_latest_json_picks_most_recent(tmp_path: Path) -> None:
    """With multiple versions, load_latest_json picks the one with newest mtime."""
    store = ArtifactStore(tmp_path / "artifacts")

    # Write version 1 (old)
    ref_old = store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data={"v": 1}
    )
    old_path = store.get_path(ref_old)
    # Backdate the old artifact
    old_time = time.time() - 100
    os.utime(old_path, (old_time, old_time))

    # Write version 2 (new) — different content, newer mtime
    store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data={"v": 2}
    )

    loaded = store.load_latest_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001"
    )
    assert loaded is not None
    assert loaded["v"] == 2


def test_partial_rebuild_picks_current_run_artifact(tmp_path: Path) -> None:
    """Simulate partial rebuild: old stale artifact + new current-run artifact.

    After a partial rebuild, the current run's artifact should be selected
    even if the old artifact has a lexicographically later content hash.
    """
    store = ArtifactStore(tmp_path / "artifacts")

    # "Run 1": write artifact with content A
    ref_a = store.put_json(
        document_id="doc",
        schema_family="s.v1",
        scope="page",
        entity_id="p0001",
        data={"run": "old", "padding": "zzz"},
    )
    # Backdate run-1 artifact to simulate old run
    old_path = store.get_path(ref_a)
    old_time = time.time() - 200
    os.utime(old_path, (old_time, old_time))

    # "Run 2": write artifact with content B (current run)
    store.put_json(
        document_id="doc",
        schema_family="s.v1",
        scope="page",
        entity_id="p0001",
        data={"run": "current"},
    )

    loaded = store.load_latest_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001"
    )
    assert loaded is not None
    assert loaded["run"] == "current"


def test_put_json_touch_on_dedup(tmp_path: Path) -> None:
    """put_json updates mtime when content already exists (dedup hit)."""
    store = ArtifactStore(tmp_path / "artifacts")
    data = {"same": "content"}

    ref = store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data=data
    )
    path = store.get_path(ref)

    # Backdate the file
    old_time = time.time() - 100
    os.utime(path, (old_time, old_time))
    mtime_before = path.stat().st_mtime

    # Write same content again — should touch
    store.put_json(
        document_id="doc", schema_family="s.v1", scope="page", entity_id="p0001", data=data
    )
    mtime_after = path.stat().st_mtime

    assert mtime_after > mtime_before


def test_put_bytes_touch_on_dedup(tmp_path: Path) -> None:
    """put_bytes updates mtime when content already exists (dedup hit)."""
    store = ArtifactStore(tmp_path / "artifacts")
    data = b"\x89PNG fake data"

    path = store.put_bytes(
        document_id="doc",
        schema_family="raster",
        scope="page",
        entity_id="p0001",
        data=data,
        extension=".png",
    )

    # Backdate
    old_time = time.time() - 100
    os.utime(path, (old_time, old_time))
    mtime_before = path.stat().st_mtime

    # Write same bytes again — should touch
    store.put_bytes(
        document_id="doc",
        schema_family="raster",
        scope="page",
        entity_id="p0001",
        data=data,
        extension=".png",
    )
    mtime_after = path.stat().st_mtime

    assert mtime_after > mtime_before


def test_resolve_latest_path_for_binary(tmp_path: Path) -> None:
    """resolve_latest_path finds the most recent binary artifact."""
    store = ArtifactStore(tmp_path / "artifacts")

    path_old = store.put_bytes(
        document_id="doc",
        schema_family="raster",
        scope="page",
        entity_id="p0001",
        data=b"old png",
        extension=".png",
    )
    # Backdate old artifact
    old_time = time.time() - 100
    os.utime(path_old, (old_time, old_time))

    path_new = store.put_bytes(
        document_id="doc",
        schema_family="raster",
        scope="page",
        entity_id="p0001",
        data=b"new png",
        extension=".png",
    )

    resolved = store.resolve_latest_path(
        document_id="doc",
        schema_family="raster",
        scope="page",
        entity_id="p0001",
        glob_pattern="*.png",
    )
    assert resolved == path_new


def test_resolve_latest_path_returns_none_when_missing(tmp_path: Path) -> None:
    """resolve_latest_path returns None when no artifact exists."""
    store = ArtifactStore(tmp_path / "artifacts")
    result = store.resolve_latest_path(
        document_id="doc",
        schema_family="raster",
        scope="page",
        entity_id="p9999",
        glob_pattern="*.png",
    )
    assert result is None
