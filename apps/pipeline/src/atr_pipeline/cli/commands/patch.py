"""CLI command: atr patch — apply a patch set to an artifact."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.stages.patch.applicator import PatchError, apply_patches
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.patch_set_v1 import PatchSetV1


def _parse_ref(ref_str: str) -> ArtifactRef:
    """Parse a relative artifact path into an ArtifactRef."""
    parts = ref_str.split("/")
    if len(parts) < 5:
        msg = f"Invalid artifact ref (need doc/family/scope/entity/file): {ref_str!r}"
        raise typer.BadParameter(msg)
    filename = parts[-1]
    c_hash = filename.rsplit(".", 1)[0] if "." in filename else filename
    return ArtifactRef(
        document_id=parts[0],
        schema_family=parts[1],
        scope=parts[2],
        entity_id=parts[3],
        content_hash=c_hash,
    )


def patch(
    doc: str,
    patch_file: Path,
    cascade: bool = False,
) -> None:
    """Apply a patch set to a target artifact."""
    if not patch_file.exists():
        typer.echo(f"Patch file not found: {patch_file}", err=True)
        raise typer.Exit(1)

    raw = json.loads(patch_file.read_text(encoding="utf-8"))
    patch_set = PatchSetV1.model_validate(raw)

    if not patch_set.target_artifact_ref:
        typer.echo("Patch set has no target_artifact_ref", err=True)
        raise typer.Exit(1)

    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)

    ref = _parse_ref(patch_set.target_artifact_ref)
    typer.echo(f"Loading artifact: {ref.relative_path}")

    try:
        artifact = store.get_json(ref)
    except FileNotFoundError as exc:
        typer.echo(f"Target artifact not found: {ref.relative_path}", err=True)
        raise typer.Exit(1) from exc

    try:
        patched = apply_patches(artifact, patch_set)
    except PatchError as exc:
        typer.echo(f"Patch failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    new_ref = store.put_json(
        document_id=ref.document_id,
        schema_family=ref.schema_family,
        scope=ref.scope,
        entity_id=ref.entity_id,
        data=patched,
    )
    typer.echo(f"Stored patched artifact: {new_ref.relative_path}")

    if cascade:
        _run_cascade(doc)


def _run_cascade(doc: str) -> None:
    """Re-run render + qa stages after patching."""
    from atr_pipeline.cli.commands.run import run as _run

    typer.echo("Cascading: re-running render → qa")
    _run(doc=doc, from_stage="render", to_stage="qa", edition="all", pages="")
