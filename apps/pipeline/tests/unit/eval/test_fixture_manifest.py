"""Tests for the fixture manifest schema, loader, and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.eval.fixture_manifest import (
    AnnotationMeta,
    FixtureManifest,
    FixtureManifestEntry,
    discover_fixture_dirs,
    load_annotation_meta,
    load_fixture_manifest,
    sha256_file,
    validate_annotation_checksums,
    validate_manifest_completeness,
    validate_source_checksums,
)

# ── Model roundtrip tests ──────────────────────────────────────────


class TestFixtureManifestEntry:
    def test_roundtrip(self) -> None:
        entry = FixtureManifestEntry(
            fixture_id="test_fixture",
            source_document="Test Doc",
            source_edition="v1",
            source_pages=[1, 2],
            source_checksum="abc123",
            redistribution="synthetic",
            redaction_status="none",
            failure_modes=["test_mode"],
            eval_dimensions=["reading_order"],
            owner="tester",
            reviewer="tester",
            retirement_policy="permanent",
        )
        data = entry.model_dump()
        restored = FixtureManifestEntry.model_validate(data)
        assert restored == entry

    def test_defaults(self) -> None:
        entry = FixtureManifestEntry(
            fixture_id="minimal",
            source_document="Doc",
            source_edition="v1",
        )
        assert entry.redistribution == "synthetic"
        assert entry.redaction_status == "none"
        assert entry.failure_modes == []


class TestAnnotationMeta:
    def test_roundtrip(self) -> None:
        meta = AnnotationMeta(
            last_refresh_timestamp="2026-03-21T00:00:00Z",
            last_refresh_issue="S5U-292",
            reviewer="tester",
            checksums={"test.json": "abc123"},
        )
        data = meta.model_dump()
        restored = AnnotationMeta.model_validate(data)
        assert restored == meta

    def test_defaults(self) -> None:
        meta = AnnotationMeta()
        assert meta.schema_version == "annotation_meta.v1"
        assert meta.annotation_format_version == 1
        assert meta.checksums == {}


class TestFixtureManifest:
    def test_roundtrip(self) -> None:
        manifest = FixtureManifest(
            fixtures=[
                FixtureManifestEntry(
                    fixture_id="test",
                    source_document="Doc",
                    source_edition="v1",
                )
            ]
        )
        data = manifest.model_dump()
        restored = FixtureManifest.model_validate(data)
        assert len(restored.fixtures) == 1
        assert restored.fixtures[0].fixture_id == "test"


# ── Loader tests ───────────────────────────────────────────────────


class TestLoadManifest:
    def test_loads_real_manifest(self) -> None:
        manifest = load_fixture_manifest()
        assert manifest.schema_version == "fixture_manifest.v1"
        assert len(manifest.fixtures) >= 7

    def test_missing_manifest_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="manifest"):
            load_fixture_manifest(repo_root=tmp_path)


class TestLoadAnnotationMeta:
    def test_loads_walking_skeleton(self) -> None:
        meta = load_annotation_meta("walking_skeleton")
        assert meta.schema_version == "annotation_meta.v1"
        assert len(meta.checksums) > 0

    def test_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Annotation meta"):
            load_annotation_meta("nonexistent", repo_root=tmp_path)


# ── Validation tests ───────────────────────────────────────────────


class TestManifestCompleteness:
    def test_real_manifest_complete(self) -> None:
        manifest = load_fixture_manifest()
        errors = validate_manifest_completeness(manifest)
        assert errors == [], f"Completeness errors: {errors}"

    def test_detects_missing_entry(self, tmp_path: Path) -> None:
        fixtures_dir = tmp_path / "packages" / "fixtures" / "sample_documents"
        (fixtures_dir / "orphan_fixture").mkdir(parents=True)
        manifest = FixtureManifest(fixtures=[])
        errors = validate_manifest_completeness(manifest, repo_root=tmp_path)
        assert any("orphan_fixture" in e for e in errors)

    def test_detects_extra_entry(self, tmp_path: Path) -> None:
        (tmp_path / "packages" / "fixtures" / "sample_documents").mkdir(parents=True)
        manifest = FixtureManifest(
            fixtures=[
                FixtureManifestEntry(
                    fixture_id="ghost",
                    source_document="Doc",
                    source_edition="v1",
                )
            ]
        )
        errors = validate_manifest_completeness(manifest, repo_root=tmp_path)
        assert any("ghost" in e for e in errors)


class TestSourceChecksums:
    def test_real_checksums_valid(self) -> None:
        manifest = load_fixture_manifest()
        errors = validate_source_checksums(manifest)
        assert errors == [], f"Checksum errors: {errors}"


class TestAnnotationChecksums:
    def test_real_walking_skeleton_valid(self) -> None:
        meta = load_annotation_meta("walking_skeleton")
        errors = validate_annotation_checksums("walking_skeleton", meta)
        assert errors == [], f"Annotation checksum errors: {errors}"

    def test_detects_mismatch(self, tmp_path: Path) -> None:
        fixtures_dir = tmp_path / "packages" / "fixtures" / "sample_documents"
        expected_dir = fixtures_dir / "test_fix" / "expected"
        expected_dir.mkdir(parents=True)
        (expected_dir / "data.json").write_text("{}", encoding="utf-8")
        meta = AnnotationMeta(checksums={"data.json": "wrong_hash"})
        errors = validate_annotation_checksums("test_fix", meta, repo_root=tmp_path)
        assert len(errors) == 1
        assert "mismatch" in errors[0]

    def test_detects_missing_file(self, tmp_path: Path) -> None:
        fixtures_dir = tmp_path / "packages" / "fixtures" / "sample_documents"
        (fixtures_dir / "test_fix" / "expected").mkdir(parents=True)
        meta = AnnotationMeta(checksums={"missing.json": "abc"})
        errors = validate_annotation_checksums("test_fix", meta, repo_root=tmp_path)
        assert any("missing" in e for e in errors)


# ── Utility tests ──────────────────────────────────────────────────


class TestSha256:
    def test_known_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty"
        p.write_bytes(b"")
        assert sha256_file(p) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestDiscoverFixtureDirs:
    def test_discovers_real_fixtures(self) -> None:
        dirs = discover_fixture_dirs()
        assert "walking_skeleton" in dirs
        assert len(dirs) >= 7
