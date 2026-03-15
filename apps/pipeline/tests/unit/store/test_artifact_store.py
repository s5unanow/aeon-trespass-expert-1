"""Tests for the immutable artifact store."""

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
