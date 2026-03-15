"""Translation validator — ensure icons survive translation."""

from __future__ import annotations

from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1


def validate_translation(
    batch: TranslationBatchV1,
    result: TranslationResultV1,
) -> list[str]:
    """Validate that translation preserves locked nodes (icons).

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    source_segments = {s.segment_id: s for s in batch.segments}

    for translated in result.segments:
        source = source_segments.get(translated.segment_id)
        if source is None:
            errors.append(f"Unknown segment: {translated.segment_id}")
            continue

        # Count icon nodes in source and target
        source_icons = [n for n in source.source_inline if n.type == "icon"]
        target_icons = [n for n in translated.target_inline if n.type == "icon"]

        if len(source_icons) != len(target_icons):
            errors.append(
                f"Icon count mismatch in {translated.segment_id}: "
                f"source={len(source_icons)}, target={len(target_icons)}"
            )

        # Check icon order
        source_ids = [n.symbol_id for n in source_icons]  # type: ignore[union-attr]
        target_ids = [n.symbol_id for n in target_icons]  # type: ignore[union-attr]
        if source_ids != target_ids:
            errors.append(
                f"Icon order mismatch in {translated.segment_id}: "
                f"source={source_ids}, target={target_ids}"
            )

    return errors
