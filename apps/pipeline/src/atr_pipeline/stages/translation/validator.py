"""Translation validator — emit QARecordV1 findings for terminology / icon issues.

Findings land on the unified QA surface (``QALayer.TERMINOLOGY``) so they flow
through waivers, ``QASummaryV1``, and ``ReviewPackV1`` like rule-based findings.
"""

from __future__ import annotations

from atr_schemas.concept_registry_v1 import ConceptRegistryV1, ConceptV1, ValidationPolicy
from atr_schemas.enums import QALayer, Severity
from atr_schemas.page_ir_v1 import IconInline
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment
from atr_schemas.translation_result_v1 import TranslatedSegment, TranslationResultV1

# QA codes emitted by the translation validator.
CODE_UNKNOWN_SEGMENT = "TRANSLATION_UNKNOWN_SEGMENT"
CODE_ICON_COUNT_MISMATCH = "TRANSLATION_ICON_COUNT_MISMATCH"
CODE_ICON_ORDER_MISMATCH = "TRANSLATION_ICON_ORDER_MISMATCH"
CODE_GLOSSARY_FORBIDDEN_TARGET = "GLOSSARY_FORBIDDEN_TARGET"
CODE_GLOSSARY_SURFACE_FORM_DRIFT = "GLOSSARY_SURFACE_FORM_DRIFT"

_SEVERITY_LOOKUP: dict[str, Severity] = {
    "info": Severity.INFO,
    "warning": Severity.WARNING,
    "error": Severity.ERROR,
    "critical": Severity.CRITICAL,
}


def _coerce_severity(raw: str, default: Severity = Severity.WARNING) -> Severity:
    """Map a validation-policy severity string onto a ``Severity`` enum."""
    return _SEVERITY_LOOKUP.get(raw.strip().lower(), default)


class _RecordContext:
    """Document/page coordinates reused by every finding on a page."""

    __slots__ = ("document_id", "page_id")

    def __init__(self, document_id: str, page_id: str | None) -> None:
        self.document_id = document_id
        self.page_id = page_id


def _make_record(
    rec_ctx: _RecordContext,
    *,
    qa_id: str,
    code: str,
    severity: Severity,
    entity_ref: str | None,
    message: str,
    values: tuple[object, object] = (None, None),
) -> QARecordV1:
    """Construct a ``QARecordV1`` with the translation validator defaults.

    ``values`` is an ``(expected, actual)`` tuple, collapsed into a single
    keyword argument to keep the parameter count small.
    """
    expected, actual = values
    return QARecordV1(
        qa_id=qa_id,
        layer=QALayer.TERMINOLOGY,
        severity=severity,
        code=code,
        document_id=rec_ctx.document_id,
        page_id=rec_ctx.page_id,
        entity_ref=entity_ref,
        message=message,
        expected=expected,
        actual=actual,
    )


def _qa_id(page_id: str | None, segment_id: str, suffix: str) -> str:
    """Build a stable ``qa_id`` for a translation finding."""
    page_part = page_id or "doc"
    return f"qa.{page_part}.translation.{segment_id}.{suffix}"


def _check_icon_parity(
    source: TranslationSegment,
    translated: TranslatedSegment,
    *,
    rec_ctx: _RecordContext,
    records: list[QARecordV1],
) -> None:
    """Emit records when the target icon set diverges from the source."""
    source_icons = [n for n in source.source_inline if n.type == "icon"]
    target_icons = [n for n in translated.target_inline if n.type == "icon"]

    if len(source_icons) != len(target_icons):
        records.append(
            _make_record(
                rec_ctx,
                qa_id=_qa_id(rec_ctx.page_id, translated.segment_id, "icon_count"),
                code=CODE_ICON_COUNT_MISMATCH,
                severity=Severity.ERROR,
                entity_ref=translated.segment_id,
                message=(
                    f"Icon count mismatch in {translated.segment_id}: "
                    f"source={len(source_icons)}, target={len(target_icons)}"
                ),
                values=(
                    {"count": len(source_icons)},
                    {"count": len(target_icons)},
                ),
            )
        )

    source_ids = [n.symbol_id for n in source_icons if isinstance(n, IconInline)]
    target_ids = [n.symbol_id for n in target_icons if isinstance(n, IconInline)]
    if source_ids != target_ids:
        records.append(
            _make_record(
                rec_ctx,
                qa_id=_qa_id(rec_ctx.page_id, translated.segment_id, "icon_order"),
                code=CODE_ICON_ORDER_MISMATCH,
                severity=Severity.ERROR,
                entity_ref=translated.segment_id,
                message=(
                    f"Icon order mismatch in {translated.segment_id}: "
                    f"source={source_ids}, target={target_ids}"
                ),
                values=(
                    {"symbol_ids": list(source_ids)},
                    {"symbol_ids": list(target_ids)},
                ),
            )
        )


def _check_forbidden_targets(
    source: TranslationSegment,
    translated: TranslatedSegment,
    *,
    rec_ctx: _RecordContext,
    records: list[QARecordV1],
) -> None:
    """Emit a record when a forbidden term appears in the translated text."""
    if not source.forbidden_targets:
        return
    target_text = " ".join(
        n.text for n in translated.target_inline if n.type == "text" and hasattr(n, "text")
    )
    for forbidden in source.forbidden_targets:
        if forbidden in target_text:
            records.append(
                _make_record(
                    rec_ctx,
                    qa_id=_qa_id(
                        rec_ctx.page_id,
                        translated.segment_id,
                        f"forbidden.{forbidden}",
                    ),
                    code=CODE_GLOSSARY_FORBIDDEN_TARGET,
                    severity=Severity.ERROR,
                    entity_ref=translated.segment_id,
                    message=(f"Forbidden term '{forbidden}' found in {translated.segment_id}"),
                    values=(
                        {"forbidden": forbidden, "must_not_contain": True},
                        {"forbidden": forbidden, "found_in_target": True},
                    ),
                )
            )


def _check_concept_realizations(
    translated: TranslatedSegment,
    concept_map: dict[str, ConceptV1],
    *,
    rec_ctx: _RecordContext,
    records: list[QARecordV1],
) -> None:
    """Emit a record when a concept realization uses a disallowed surface form."""
    if not translated.concept_realizations:
        return
    for cr in translated.concept_realizations:
        concept = concept_map.get(cr.concept_id)
        if concept is None:
            continue
        allowed = concept.target.allowed_surface_forms
        if not allowed:
            continue
        allowed_lower = {f.lower() for f in allowed}
        if cr.surface_form.lower() in allowed_lower:
            continue
        policy: ValidationPolicy = concept.validation_policy
        severity = _coerce_severity(policy.non_preferred_allowed)
        records.append(
            _make_record(
                rec_ctx,
                qa_id=_qa_id(
                    rec_ctx.page_id,
                    translated.segment_id,
                    f"surface_form.{cr.concept_id}",
                ),
                code=CODE_GLOSSARY_SURFACE_FORM_DRIFT,
                severity=severity,
                entity_ref=translated.segment_id,
                message=(
                    f"Concept {cr.concept_id} surface form "
                    f"'{cr.surface_form}' not in allowed forms: {list(allowed)}"
                ),
                values=(
                    {
                        "concept_id": cr.concept_id,
                        "allowed_surface_forms": list(allowed),
                    },
                    {
                        "concept_id": cr.concept_id,
                        "surface_form": cr.surface_form,
                    },
                ),
            )
        )


def validate_translation(
    batch: TranslationBatchV1,
    result: TranslationResultV1,
    *,
    concept_registry: ConceptRegistryV1 | None = None,
    document_id: str = "",
    page_id: str | None = None,
) -> list[QARecordV1]:
    """Validate a translation result against its batch.

    Returns a list of ``QARecordV1`` findings (empty when the translation is clean).
    Findings carry ``layer=QALayer.TERMINOLOGY`` and stable ``code`` values so the
    downstream QA stage can aggregate, tally, and waive them uniformly.
    """
    records: list[QARecordV1] = []
    source_segments = {s.segment_id: s for s in batch.segments}
    rec_ctx = _RecordContext(document_id=document_id, page_id=page_id)

    concept_map: dict[str, ConceptV1] = {}
    if concept_registry:
        concept_map = {c.concept_id: c for c in concept_registry.concepts}

    for translated in result.segments:
        source = source_segments.get(translated.segment_id)
        if source is None:
            records.append(
                _make_record(
                    rec_ctx,
                    qa_id=_qa_id(page_id, translated.segment_id, "unknown_segment"),
                    code=CODE_UNKNOWN_SEGMENT,
                    severity=Severity.ERROR,
                    entity_ref=translated.segment_id,
                    message=f"Unknown segment: {translated.segment_id}",
                    values=(
                        {"segment_id_known": True},
                        {"segment_id": translated.segment_id},
                    ),
                )
            )
            continue

        _check_icon_parity(source, translated, rec_ctx=rec_ctx, records=records)
        _check_forbidden_targets(source, translated, rec_ctx=rec_ctx, records=records)
        if concept_registry:
            _check_concept_realizations(
                translated,
                concept_map,
                rec_ctx=rec_ctx,
                records=records,
            )

    return records
