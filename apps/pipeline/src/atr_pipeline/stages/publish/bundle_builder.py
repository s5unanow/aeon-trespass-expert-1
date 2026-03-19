"""Build a local release bundle: static data + web app build."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from atr_pipeline.utils.hashing import sha256_file, sha256_str
from atr_schemas.build_manifest_v1 import BuildManifestV1, ReleaseFile

# Map from RenderResult ref field names to bundle filenames
_COMPANION_NAMES: dict[str, str] = {
    "glossary_ref": "glossary.json",
    "search_docs_ref": "search_docs.json",
    "nav_ref": "nav.json",
}


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
        msg = f"Artifact not found: {ref}"
        raise FileNotFoundError(msg)
    dest = data_dir / dest_name
    shutil.copy2(src, dest)
    files.append(
        ReleaseFile(
            path=f"data/{dest_name}",
            sha256=sha256_file(dest),
            size_bytes=dest.stat().st_size,
        )
    )


def _compute_build_id(
    render_page_refs: dict[str, str],
    companion_refs: dict[str, str],
) -> str:
    """Derive a deterministic build id from all input artifact refs.

    Two calls with the same refs produce the same id.
    """
    parts: list[str] = []
    for page_id in sorted(render_page_refs):
        parts.append(f"page:{page_id}={render_page_refs[page_id]}")
    for key in sorted(companion_refs):
        parts.append(f"companion:{key}={companion_refs[key]}")
    digest = sha256_str("\n".join(parts))[:12]
    return f"build_{digest}"


def build_release_bundle(
    *,
    document_id: str,
    artifact_root: Path,
    web_dist: Path | None = None,
    output_dir: Path,
    pipeline_version: str = "",
    render_page_refs: dict[str, str],
    companion_refs: dict[str, str] | None = None,
) -> BuildManifestV1:
    """Build a self-contained static release directory.

    All bundle inputs are selected by explicit artifact refs — no
    filesystem enumeration or first-file heuristics.

    *render_page_refs*: page_id → artifact ref path for render pages.
    *companion_refs*: key → artifact ref path for glossary, search_docs, nav.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    files: list[ReleaseFile] = []
    resolved_companions = companion_refs or {}

    # Copy render pages by explicit ref
    for page_id in sorted(render_page_refs):
        dest_name = f"render_page.{page_id}.json"
        _copy_ref_artifact(artifact_root, render_page_refs[page_id], dest_name, data_dir, files)

    # Copy companion artifacts by explicit ref
    for ref_key, dest_name in _COMPANION_NAMES.items():
        ref = resolved_companions.get(ref_key, "")
        if ref:
            _copy_ref_artifact(artifact_root, ref, dest_name, data_dir, files)

    # Copy web app dist if available
    if web_dist and web_dist.exists():
        app_dir = output_dir / "app"
        if app_dir.exists():
            shutil.rmtree(app_dir)
        shutil.copytree(web_dist, app_dir)

    # Content-addressed build identity
    build_id = _compute_build_id(render_page_refs, resolved_companions)
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
