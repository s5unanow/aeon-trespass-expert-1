"""Pydantic models and loaders for the fixture manifest and annotation metadata."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from atr_pipeline.config.loader import _find_repo_root

FIXTURES_DIR = "packages/fixtures/sample_documents"
MANIFEST_PATH = "packages/fixtures/manifest.toml"


class FixtureManifestEntry(BaseModel):
    """A single fixture's provenance, ownership, and coverage metadata."""

    fixture_id: str
    source_document: str
    source_edition: str
    source_pages: list[int] = Field(default_factory=list)
    source_checksum: str = ""
    redistribution: Literal["synthetic", "redacted", "fair_use_fragment"] = "synthetic"
    redaction_status: Literal["none", "partial", "full"] = "none"
    failure_modes: list[str] = Field(default_factory=list)
    eval_dimensions: list[str] = Field(default_factory=list)
    owner: str = ""
    reviewer: str = ""
    retirement_policy: str = ""
    notes: str = ""


class AnnotationMeta(BaseModel):
    """Sidecar metadata for a fixture's expected/ directory."""

    schema_version: str = "annotation_meta.v1"
    annotation_format_version: int = 1
    last_refresh_timestamp: str = ""
    last_refresh_issue: str = ""
    last_refresh_commit: str = ""
    reviewer: str = ""
    checksums: dict[str, str] = Field(default_factory=dict)


class FixtureManifest(BaseModel):
    """Top-level manifest containing all fixture entries."""

    schema_version: str = "fixture_manifest.v1"
    fixtures: list[FixtureManifestEntry] = Field(default_factory=list)


def load_fixture_manifest(*, repo_root: Path | None = None) -> FixtureManifest:
    """Load the fixture manifest from packages/fixtures/manifest.toml."""
    root = repo_root or _find_repo_root()
    path = root / MANIFEST_PATH
    if not path.exists():
        msg = f"Fixture manifest not found: {path}"
        raise FileNotFoundError(msg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return FixtureManifest.model_validate(data)


def load_annotation_meta(fixture_id: str, *, repo_root: Path | None = None) -> AnnotationMeta:
    """Load annotation metadata for a fixture's expected/ directory."""
    root = repo_root or _find_repo_root()
    path = root / FIXTURES_DIR / fixture_id / "expected" / "_annotation_meta.toml"
    if not path.exists():
        msg = f"Annotation meta not found: {path}"
        raise FileNotFoundError(msg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return AnnotationMeta.model_validate(data)


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_fixture_dirs(*, repo_root: Path | None = None) -> list[str]:
    """Return sorted fixture directory names under packages/fixtures/sample_documents/."""
    root = repo_root or _find_repo_root()
    fixtures_dir = root / FIXTURES_DIR
    if not fixtures_dir.is_dir():
        return []
    return sorted(
        d.name for d in fixtures_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def validate_manifest_completeness(
    manifest: FixtureManifest, *, repo_root: Path | None = None
) -> list[str]:
    """Check every fixture directory has a manifest entry. Returns error messages."""
    dirs = discover_fixture_dirs(repo_root=repo_root)
    manifest_ids = {e.fixture_id for e in manifest.fixtures}
    errors: list[str] = []
    for d in dirs:
        if d not in manifest_ids:
            errors.append(f"Fixture directory '{d}' has no manifest entry")
    for fid in manifest_ids:
        if fid not in dirs:
            errors.append(f"Manifest entry '{fid}' has no fixture directory")
    return errors


def validate_source_checksums(
    manifest: FixtureManifest, *, repo_root: Path | None = None
) -> list[str]:
    """Verify source_checksum in each manifest entry matches the primary PDF."""
    root = repo_root or _find_repo_root()
    errors: list[str] = []
    for entry in manifest.fixtures:
        if not entry.source_checksum:
            continue
        source_dir = root / FIXTURES_DIR / entry.fixture_id / "source"
        pdfs = sorted(source_dir.glob("*.pdf"))
        if not pdfs:
            errors.append(f"Fixture '{entry.fixture_id}': no PDF in source/")
            continue
        actual = sha256_file(pdfs[0])
        if actual != entry.source_checksum:
            errors.append(
                f"Fixture '{entry.fixture_id}': checksum mismatch "
                f"(manifest={entry.source_checksum[:12]}… actual={actual[:12]}…)"
            )
    return errors


def validate_annotation_checksums(
    fixture_id: str, meta: AnnotationMeta, *, repo_root: Path | None = None
) -> list[str]:
    """Verify checksums in annotation metadata match actual expected/ files.

    Checks both directions: meta entries must match disk, and JSON files on
    disk must have a corresponding meta entry.
    """
    root = repo_root or _find_repo_root()
    expected_dir = root / FIXTURES_DIR / fixture_id / "expected"
    errors: list[str] = []
    for filename, expected_hash in meta.checksums.items():
        path = expected_dir / filename
        if not path.exists():
            errors.append(f"Fixture '{fixture_id}': expected file missing: {filename}")
            continue
        actual = sha256_file(path)
        if actual != expected_hash:
            errors.append(
                f"Fixture '{fixture_id}/{filename}': checksum mismatch "
                f"(meta={expected_hash[:12]}… actual={actual[:12]}…)"
            )
    # Reverse check: JSON files on disk not tracked in annotation meta
    if expected_dir.is_dir():
        tracked = set(meta.checksums)
        for path in sorted(expected_dir.glob("*.json")):
            if path.name not in tracked:
                errors.append(f"Fixture '{fixture_id}': untracked expected file: {path.name}")
    return errors


def load_fixture_page_ir(
    fixture_id: str,
    page_id: str,
    *,
    lang: str = "en",
    repo_root: Path | None = None,
) -> dict[str, object] | None:
    """Load page IR JSON from a checked-in fixture's expected/ directory.

    Returns parsed JSON dict, or None if the file does not exist.
    """
    root = repo_root or _find_repo_root()
    path = root / FIXTURES_DIR / fixture_id / "expected" / f"page_ir.{lang}.{page_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]
