"""Build a local release bundle: static data + web app build."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from atr_pipeline.utils.hashing import sha256_file
from atr_schemas.build_manifest_v1 import BuildManifestV1, ReleaseFile


def _copy_single_artifact(
    src_dir: Path, dest_name: str, data_dir: Path, files: list[ReleaseFile]
) -> None:
    """Copy the first JSON file from *src_dir* into *data_dir*."""
    if not src_dir.exists():
        return
    for json_file in src_dir.rglob("*.json"):
        dest = data_dir / dest_name
        shutil.copy2(json_file, dest)
        files.append(
            ReleaseFile(
                path=f"data/{dest_name}",
                sha256=sha256_file(dest),
                size_bytes=dest.stat().st_size,
            )
        )
        break


def _copy_ref_artifact(
    artifact_root: Path,
    ref: str,
    dest_name: str,
    data_dir: Path,
    files: list[ReleaseFile],
) -> None:
    """Copy a specific artifact by ref path into *data_dir*."""
    src = artifact_root / ref
    if not src.exists():
        return
    dest = data_dir / dest_name
    shutil.copy2(src, dest)
    files.append(
        ReleaseFile(
            path=f"data/{dest_name}",
            sha256=sha256_file(dest),
            size_bytes=dest.stat().st_size,
        )
    )


def build_release_bundle(
    *,
    document_id: str,
    artifact_root: Path,
    web_dist: Path | None = None,
    output_dir: Path,
    pipeline_version: str = "",
    render_page_refs: dict[str, str] | None = None,
) -> BuildManifestV1:
    """Build a self-contained static release directory.

    When *render_page_refs* is provided (page_id → artifact ref path),
    copies those exact artifacts. Otherwise falls back to filesystem
    enumeration for backward compatibility.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    files: list[ReleaseFile] = []

    if render_page_refs:
        _copy_render_from_refs(artifact_root, render_page_refs, data_dir, files)
    else:
        _copy_render_from_fs(artifact_root, document_id, data_dir, files)

    # Copy singleton artifacts (glossary, search docs, nav)
    doc_root = artifact_root / document_id
    _copy_single_artifact(doc_root / "glossary_payload.v1", "glossary.json", data_dir, files)
    _copy_single_artifact(doc_root / "search_docs.v1", "search_docs.json", data_dir, files)
    _copy_single_artifact(doc_root / "nav.v1", "nav.json", data_dir, files)

    # Copy web app dist if available
    if web_dist and web_dist.exists():
        app_dir = output_dir / "app"
        if app_dir.exists():
            shutil.rmtree(app_dir)
        shutil.copytree(web_dist, app_dir)

    # Build manifest
    build_id = f"build_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    manifest = BuildManifestV1(
        build_id=build_id,
        document_id=document_id,
        content_version=f"{document_id}.{build_id}",
        generated_at=datetime.now(UTC).isoformat(),
        pipeline_version=pipeline_version,
        files=files,
    )

    # Write manifest
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return manifest


def _copy_render_from_refs(
    artifact_root: Path,
    page_refs: dict[str, str],
    data_dir: Path,
    files: list[ReleaseFile],
) -> None:
    """Copy render pages using explicit artifact refs."""
    for page_id in sorted(page_refs):
        dest_name = f"render_page.{page_id}.json"
        _copy_ref_artifact(artifact_root, page_refs[page_id], dest_name, data_dir, files)


def _copy_render_from_fs(
    artifact_root: Path,
    document_id: str,
    data_dir: Path,
    files: list[ReleaseFile],
) -> None:
    """Copy render pages by filesystem enumeration (legacy fallback)."""
    render_dir = artifact_root / document_id / "render_page.v1" / "page"
    if not render_dir.exists():
        return
    for page_dir in sorted(render_dir.iterdir()):
        if page_dir.is_dir():
            for json_file in page_dir.glob("*.json"):
                dest_name = f"render_page.{page_dir.name}.json"
                dest = data_dir / dest_name
                shutil.copy2(json_file, dest)
                files.append(
                    ReleaseFile(
                        path=f"data/{dest_name}",
                        sha256=sha256_file(dest),
                        size_bytes=dest.stat().st_size,
                    )
                )
                break  # take latest only
