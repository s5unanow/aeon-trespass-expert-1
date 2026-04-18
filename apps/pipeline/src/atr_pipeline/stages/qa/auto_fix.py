"""Auto-fix patch generation from QA findings.

Takes QA records that have ``auto_fix.available=True`` and the render page
they refer to, then produces a :class:`PatchSetV1` with deterministic
patch operations applicable via :mod:`atr_pipeline.stages.patch.applicator`.

## Rule coverage (inventory for S5U-598)

Rules that *do* emit ``auto_fix``:

- ``paragraph_length`` → ``split_paragraph`` — sentence-boundary split
- ``decorative_icon`` → ``remove_decorative`` — regex strip of asset tokens
  and private-use glyphs
- ``duplicate_content`` → ``delete_duplicate`` — delete the second of a
  near-duplicate consecutive block pair

Rules that *do not* emit ``auto_fix`` (by design):

- ``dead_page_ref`` — pruning changes reading flow; requires translator
  review (the pruned reference typically points at a target that needs
  replacement, not removal)
- ``leaked_identifier`` — masking would elide content; ERROR severity
  already routes these to the review pack
- ``icon_count`` — cross-IR parity issue; no single-block textual fix
- ``glued_text`` — requires re-extraction, not a textual patch
- ``untranslated_text`` — requires translate stage, not patchable

## Output

Generated patch sets set ``target_artifact_ref`` / ``target_kind`` so
that :mod:`atr_pipeline.cli.commands.patch` (or the in-process
applicator) can apply them to the source ``render_page.v1`` artifact.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from atr_pipeline.stages.qa.rules.decorative_icon_rule import DECORATIVE_PATTERNS
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_schemas.enums import PatchScope, PatchTargetKind
from atr_schemas.patch_set_v1 import PatchOperation, PatchSetV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import (
    RenderDividerBlock,
    RenderPageV1,
    RenderTextInline,
)

logger = logging.getLogger(__name__)

# ── Sentence boundary for paragraph splitting ─────────────────────────

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u0410-\u042F\u0401])")


# ── Public API ────────────────────────────────────────────────────────


def generate_patches_for_page(
    records: list[QARecordV1],
    render_page: RenderPageV1,
    *,
    target_ref: ArtifactRef | None = None,
) -> PatchSetV1 | None:
    """Build a :class:`PatchSetV1` for all auto-fixable records on one page.

    Records with ``waived=True`` are skipped unconditionally. When
    *target_ref* is provided, it is stamped onto the patch set so the
    result is directly applicable via ``atr patch``.

    Returns ``None`` when no records are fixable.
    """
    fixable = [r for r in records if r.auto_fix and r.auto_fix.available and not r.waived]
    if not fixable:
        return None

    ops: list[PatchOperation] = []

    # 1. Text-level replacements (no index shifts)
    for r in fixable:
        if r.auto_fix and r.auto_fix.fixer == "remove_decorative":
            ops.extend(_fix_remove_decorative(r, render_page))

    # 2. Structural changes — process highest block index first so that
    #    delete/insert ops on earlier indices remain valid.
    ops.extend(_collect_structural_ops(fixable, render_page))

    if not ops:
        return None

    page_id = render_page.page.id
    return PatchSetV1(
        patch_id=f"auto-fix-{page_id}-{uuid.uuid4().hex[:8]}",
        target_artifact_ref=target_ref.relative_path if target_ref else "",
        target_kind=PatchTargetKind.RENDER_PAGE,
        operations=ops,
        reason="Auto-generated fixes from QA findings",
        author="qa-auto-fix",
    )


def _collect_structural_ops(
    fixable: list[QARecordV1],
    render_page: RenderPageV1,
) -> list[PatchOperation]:
    """Gather delete/insert ops sorted by descending block index."""
    structural: list[tuple[int, list[PatchOperation]]] = []
    for r in fixable:
        if not (r.auto_fix and r.entity_ref):
            continue
        idx = _find_block_index(render_page, r.entity_ref)
        if idx is None:
            continue
        if r.auto_fix.fixer == "delete_duplicate":
            structural.append(
                (
                    idx,
                    [
                        PatchOperation(
                            op="delete",
                            path=f"/blocks/{idx}",
                            scope=PatchScope.BLOCK_STRUCTURE,
                        ),
                    ],
                )
            )
        elif r.auto_fix.fixer == "split_paragraph":
            split_ops = _fix_split_paragraph(render_page, idx)
            if split_ops:
                structural.append((idx, split_ops))
        elif r.auto_fix.fixer != "remove_decorative":
            logger.warning("Unknown fixer %s in %s", r.auto_fix.fixer, r.qa_id)

    structural.sort(key=lambda x: x[0], reverse=True)
    ops: list[PatchOperation] = []
    for _, s_ops in structural:
        ops.extend(s_ops)
    return ops


# ── Decorative removal ───────────────────────────────────────────────


def _fix_remove_decorative(
    record: QARecordV1,
    page: RenderPageV1,
) -> list[PatchOperation]:
    """Generate replace ops to strip decorative chars from text children."""
    if not record.entity_ref:
        return []
    idx = _find_block_index(page, record.entity_ref)
    if idx is None:
        return []
    block = page.blocks[idx]
    if isinstance(block, RenderDividerBlock):
        return []

    ops: list[PatchOperation] = []
    for ci, child in enumerate(block.children):
        if child.kind != "text":
            continue
        cleaned = _strip_decorative(child.text)
        if cleaned != child.text:
            ops.append(
                PatchOperation(
                    op="replace",
                    path=f"/blocks/{idx}/children/{ci}/text",
                    value=cleaned,
                    scope=PatchScope.TEXT,
                )
            )
    return ops


def _strip_decorative(text: str) -> str:
    """Remove all decorative patterns from *text*."""
    result = text
    for pattern in DECORATIVE_PATTERNS:
        result = pattern.sub("", result)
    return re.sub(r"  +", " ", result).strip()


# ── Paragraph splitting ──────────────────────────────────────────────


def _fix_split_paragraph(
    page: RenderPageV1,
    block_idx: int,
) -> list[PatchOperation]:
    """Split a long block at the nearest sentence boundary to the midpoint."""
    block = page.blocks[block_idx]
    if isinstance(block, RenderDividerBlock):
        return []

    full_text = "".join(child.text for child in block.children if child.kind == "text")
    if not full_text:
        return []

    boundary = _find_sentence_boundary(full_text, len(full_text) // 2)
    if boundary is None:
        return []

    split_end, second_start = boundary
    first_children, second_children = _split_children_at(
        block.children,
        split_end,
        second_start,
    )
    if not first_children or not second_children:
        return []

    first_ser = [_serialize_inline(c) for c in first_children]
    second_ser = [_serialize_inline(c) for c in second_children]
    new_block: dict[str, Any] = block.model_dump()
    new_block["id"] = f"{block.id}_split"
    new_block["children"] = second_ser

    return [
        PatchOperation(
            op="replace",
            path=f"/blocks/{block_idx}/children",
            value=first_ser,
            scope=PatchScope.BLOCK_STRUCTURE,
        ),
        PatchOperation(
            op="insert",
            path=f"/blocks/{block_idx + 1}",
            value=new_block,
            scope=PatchScope.BLOCK_STRUCTURE,
        ),
    ]


def _find_sentence_boundary(
    text: str,
    near: int,
) -> tuple[int, int] | None:
    """Return ``(first_end, second_start)`` for the boundary nearest *near*."""
    matches = list(_SENTENCE_RE.finditer(text))
    if not matches:
        return None
    best = min(matches, key=lambda m: abs(m.start() - near))
    return best.start(), best.end()


def _split_children_at(
    children: list[Any],
    first_end: int,
    second_start: int,
) -> tuple[list[Any], list[Any]]:
    """Split inline children at text positions *first_end* / *second_start*."""
    first: list[Any] = []
    second: list[Any] = []
    pos = 0
    split_done = False

    for child in children:
        if split_done:
            second.append(child)
            continue
        if child.kind != "text":
            first.append(child)
            continue

        end_pos = pos + len(child.text)
        if end_pos <= first_end:
            first.append(child)
            pos = end_pos
        elif pos >= second_start:
            second.append(child)
            split_done = True
        else:
            left = child.text[: first_end - pos]
            right = child.text[second_start - pos :]
            if left:
                first.append(_clone_text(child, left))
            if right:
                second.append(_clone_text(child, right))
            split_done = True

    return first, second


# ── Helpers ───────────────────────────────────────────────────────────


def _find_block_index(page: RenderPageV1, block_id: str) -> int | None:
    for i, block in enumerate(page.blocks):
        if block.id == block_id:
            return i
    return None


def _serialize_inline(child: Any) -> dict[str, Any]:
    return child.model_dump()  # type: ignore[no-any-return]


def _clone_text(original: Any, new_text: str) -> RenderTextInline:
    """Clone a text inline node with different text content."""
    return RenderTextInline(text=new_text, marks=list(original.marks))
