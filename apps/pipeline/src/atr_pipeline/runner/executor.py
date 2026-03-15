"""Stage executor — runs stages with cache checking and event recording."""

from __future__ import annotations

import time

from pydantic import BaseModel

from atr_pipeline.registry.events import (
    find_cached_event,
    record_stage_finish,
    record_stage_start,
)
from atr_pipeline.runner.cache_keys import build_cache_key
from atr_pipeline.runner.result import StageResult
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.runner.stage_protocol import Stage
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.utils.hashing import content_hash


def execute_stage(
    stage: Stage,
    ctx: StageContext,
    *,
    input_data: BaseModel | None = None,
    input_hashes: list[str] | None = None,
    config_hash: str = "",
) -> StageResult:
    """Execute a stage with cache checking and registry recording.

    If a completed event with the same cache key exists, returns a cached result.
    Otherwise runs the stage, records the event, and returns the result.
    """
    # Build cache key
    i_hashes = input_hashes or []
    if input_data is not None and not i_hashes:
        i_hashes = [content_hash(input_data.model_dump())]

    cache_key = build_cache_key(
        stage_name=stage.name,
        stage_version=stage.version,
        schema_version="v1",
        config_hash=config_hash or content_hash(ctx.config.model_dump(mode="json")),
        input_hashes=i_hashes,
    )

    # Check cache
    cached_event = find_cached_event(ctx.registry_conn, cache_key=cache_key)
    if cached_event is not None:
        cached_ref_str = cached_event["artifact_ref"]
        ctx.logger.info("Cache hit for %s (key=%s)", stage.name, cache_key)
        return StageResult(
            stage_name=stage.name,
            cache_key=cache_key,
            cached=True,
            artifact_ref=_parse_artifact_ref(cached_ref_str) if cached_ref_str else None,
        )

    # Run stage
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name=stage.name,
        scope=stage.scope.value,
        entity_id=ctx.document_id,
        cache_key=cache_key,
    )

    start = time.monotonic()
    try:
        output = stage.run(ctx, input_data)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Store output artifact
        ref = ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family=stage.name,
            scope=stage.scope.value,
            entity_id=ctx.document_id,
            data=output,
        )

        record_stage_finish(
            ctx.registry_conn,
            event_id=event_id,
            status="completed",
            artifact_ref=ref.relative_path,
            duration_ms=duration_ms,
        )

        return StageResult(
            stage_name=stage.name,
            cache_key=cache_key,
            cached=False,
            artifact_ref=ref,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        record_stage_finish(
            ctx.registry_conn,
            event_id=event_id,
            status="failed",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        return StageResult(
            stage_name=stage.name,
            cache_key=cache_key,
            cached=False,
            error=str(exc),
        )


def _parse_artifact_ref(ref_str: str) -> ArtifactRef | None:
    """Parse a relative path back into an ArtifactRef."""
    parts = ref_str.split("/")
    if len(parts) < 5:
        return None
    filename = parts[-1]
    c_hash = filename.rsplit(".", 1)[0] if "." in filename else filename
    return ArtifactRef(
        document_id=parts[0],
        schema_family=parts[1],
        scope=parts[2],
        entity_id=parts[3],
        content_hash=c_hash,
    )
