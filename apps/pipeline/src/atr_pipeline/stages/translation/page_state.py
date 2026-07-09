"""Per-page translation resume state (S5U-1228).

``TranslationStage.run()`` loops over every page and calls the (expensive) LLM
``translate_batch`` for each one. Before S5U-1228 a single failed page raised
out of the loop, the executor recorded the stage event as ``status='failed'``,
and on retry the executor cache MISSED (it matches only ``status='completed'``)
so the entire stage re-translated every page from scratch — discarding the LLM
spend already incurred for the pages that had completed. For the 83-page RU
edition (S5U-997) that is hours of work lost to one transient failure.

This module adds a per-page resume cache. Each fully-translated page persists a
small ``translation_resume.v1`` record. On retry the stage reads the record back
and, if it is still valid for the current EN source, skips the LLM call and
reuses the already-persisted RU IR — resuming from the first incomplete page.

The resume cache is a second, finer-grained layer beneath the executor's
stage-level cache: a fully-successful run still hits the executor cache and skips
``run()`` entirely; only a failed-mid-run retry re-enters ``run()`` and benefits
from per-page resume.

Validity is keyed on the EN IR content hash and, for opt-in model routing, the
translation configuration. A changed source or routing policy can therefore
never reuse a stale RU translation. Reads are fail-safe: a missing,
unparseable, hash-mismatched, or dangling-ref record yields ``None`` ("no
resume state — re-translate") and is logged; it never crashes and never
silently reuses wrong content.
"""

from __future__ import annotations

import json
from logging import Logger
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from atr_pipeline.config.models import TranslationConfig
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.utils.hashing import content_hash
from atr_schemas.page_ir_v1 import PageIRV1

#: Artifact family for the per-page resume record. ``put_json`` writes it
#: atomically (temp file + ``os.replace``) via ``atomic_write_text``.
RESUME_SCHEMA_FAMILY = "translation_resume.v1"


class ResumeStageContext(Protocol):
    """Subset of ``StageContext`` used by the resume cache.

    Declared as a Protocol (mirroring ``critic_stage._StageContextLike`` and
    ``repair_helpers.RepairStageContext``) so this helper module does not import
    ``atr_pipeline.runner`` — the ``stages -> runner`` layer contract only
    whitelists the entry-point ``stage.py`` modules.
    """

    document_id: str
    artifact_store: ArtifactStore
    logger: Logger


class PageResumeState(BaseModel):
    """Per-page record marking a page as fully translated in a prior run.

    Persisted only after the page's RU IR + meta + QA artifacts are all on
    disk, so its presence means "this page completed". ``en_ir_content_hash``
    always guards the source. ``translation_config_hash`` additionally guards
    enabled model routing; it remains absent for disabled routing so legacy
    resume artifacts and behavior stay unchanged.
    """

    page_id: str
    en_ir_content_hash: str
    translation_config_hash: str | None = None
    ru_ir_ref: str
    warning_count: int = Field(ge=0)


def en_ir_content_hash(en_ir: PageIRV1) -> str:
    """Stable content hash of an EN ``PageIRV1`` (the resume validity key)."""
    return content_hash(en_ir.model_dump(mode="json"))


def translation_config_hash(config: TranslationConfig) -> str:
    """Stable hash of every translation setting that can affect page output."""
    return content_hash(config.model_dump(mode="json"))


def _ru_ir_ref_exists(ctx: ResumeStageContext, ru_ir_ref: str) -> bool:
    """Return True if the RU IR artifact named by ``ru_ir_ref`` is on disk.

    A resume record whose RU IR was cleaned up (``make clean`` leaves the
    registry intact, partial cleanup, fresh checkout) must not be reused — the
    page must re-translate so it self-heals.
    """
    target = ctx.artifact_store.root / ru_ir_ref
    return target.exists()


def load_resume_state(
    ctx: ResumeStageContext,
    page_id: str,
    *,
    expected_en_hash: str,
    expected_config_hash: str | None = None,
) -> PageResumeState | None:
    """Load a valid resume record for ``page_id`` or return ``None``.

    Returns the record ONLY when all of the following hold:

    * a ``translation_resume.v1`` artifact exists for the page,
    * it parses as :class:`PageResumeState`,
    * its ``en_ir_content_hash`` equals ``expected_en_hash`` (EN source
      unchanged since the cached translation), and
    * its optional ``translation_config_hash`` equals ``expected_config_hash``
      (enabled routing policy unchanged), and
    * the referenced RU IR artifact still exists on disk.

    On ANY failure — missing, corrupt/partial JSON, validation error, hash
    mismatch, or dangling RU ref — returns ``None`` and logs the reason. This
    is the fail-safe contract (S5U-1228 constraint 3): never crash, never
    reuse wrong content; the caller re-translates from scratch.
    """
    try:
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family=RESUME_SCHEMA_FAMILY,
            scope="page",
            entity_id=page_id,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        # ``load_latest_json`` reads + ``json.load``s the latest file; a
        # truncated/garbled file surfaces here. Treat as "no resume state".
        ctx.logger.warning("Resume state for %s unreadable (%s); will re-translate", page_id, exc)
        return None

    if data is None:
        return None

    try:
        state = PageResumeState.model_validate(data)
    except ValidationError as exc:
        ctx.logger.warning(
            "Resume state for %s failed validation (%s); will re-translate", page_id, exc
        )
        return None

    if state.en_ir_content_hash != expected_en_hash:
        ctx.logger.info("Resume state for %s stale (EN IR changed); will re-translate", page_id)
        return None

    if state.translation_config_hash != expected_config_hash:
        ctx.logger.info(
            "Resume state for %s stale (translation config changed); will re-translate",
            page_id,
        )
        return None

    if not _ru_ir_ref_exists(ctx, state.ru_ir_ref):
        ctx.logger.warning(
            "Resume state for %s references missing RU IR %s; will re-translate",
            page_id,
            state.ru_ir_ref,
        )
        return None

    return state


def persist_resume_state(
    ctx: ResumeStageContext,
    *,
    page_id: str,
    en_ir_hash: str,
    config_hash: str | None = None,
    ru_ir_ref: ArtifactRef,
    warning_count: int,
) -> None:
    """Persist the per-page resume record (incremental success marker).

    Called only after the page's RU IR has been written, so the record's
    presence is a durable "this page completed" signal. Written atomically via
    ``put_json`` → ``atomic_write_text`` (temp file + ``os.replace``).
    """
    state = PageResumeState(
        page_id=page_id,
        en_ir_content_hash=en_ir_hash,
        translation_config_hash=config_hash,
        ru_ir_ref=ru_ir_ref.relative_path,
        warning_count=warning_count,
    )
    ctx.artifact_store.put_json(
        document_id=ctx.document_id,
        schema_family=RESUME_SCHEMA_FAMILY,
        scope="page",
        entity_id=page_id,
        data=state.model_dump(mode="json", exclude_none=True),
    )
