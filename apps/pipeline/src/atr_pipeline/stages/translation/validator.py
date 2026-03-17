"""Translation validator — ensure icons survive and terminology is correct."""

from __future__ import annotations

from atr_schemas.concept_registry_v1 import ConceptRegistryV1, ConceptV1
from atr_schemas.page_ir_v1 import IconInline
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1


def validate_translation(
    batch: TranslationBatchV1,
    result: TranslationResultV1,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
) -> list[str]:
    """Validate that translation preserves locked nodes and respects terminology.

    Returns a list of error/warning messages (empty if valid).
    """
    errors: list[str] = []

    source_segments = {s.segment_id: s for s in batch.segments}

    # Build concept lookup for surface form validation
    concept_map: dict[str, ConceptV1] = {}
    if concept_registry:
        concept_map = {c.concept_id: c for c in concept_registry.concepts}

    for translated in result.segments:
        source = source_segments.get(translated.segment_id)
        if source is None:
            errors.append(f"Unknown segment: {translated.segment_id}")
            continue

        # --- Icon count and order ---
        source_icons = [n for n in source.source_inline if n.type == "icon"]
        target_icons = [n for n in translated.target_inline if n.type == "icon"]

        if len(source_icons) != len(target_icons):
            errors.append(
                f"Icon count mismatch in {translated.segment_id}: "
                f"source={len(source_icons)}, target={len(target_icons)}"
            )

        source_ids = [
            n.symbol_id for n in source_icons if isinstance(n, IconInline)
        ]
        target_ids = [
            n.symbol_id for n in target_icons if isinstance(n, IconInline)
        ]
        if source_ids != target_ids:
            errors.append(
                f"Icon order mismatch in {translated.segment_id}: "
                f"source={source_ids}, target={target_ids}"
            )

        # --- Forbidden target text ---
        if source.forbidden_targets:
            target_text = " ".join(
                n.text
                for n in translated.target_inline
                if n.type == "text" and hasattr(n, "text")
            )
            for forbidden in source.forbidden_targets:
                if forbidden in target_text:
                    errors.append(
                        f"Forbidden term '{forbidden}' found in "
                        f"{translated.segment_id}"
                    )

        # --- Concept realization surface forms ---
        if concept_registry and translated.concept_realizations:
            for cr in translated.concept_realizations:
                concept = concept_map.get(cr.concept_id)
                if concept is None:
                    continue
                allowed = concept.target.allowed_surface_forms
                if allowed and cr.surface_form not in allowed:
                    policy = concept.validation_policy
                    severity = policy.non_preferred_allowed
                    errors.append(
                        f"[{severity}] Concept {cr.concept_id} surface form "
                        f"'{cr.surface_form}' not in allowed forms: {allowed}"
                    )

    return errors
