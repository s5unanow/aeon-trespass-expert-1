"""PublicQARecordSetV1 — public-facing QA records list for the web bundle (S5U-689).

A wrapper around a list of ``PublicQARecordV1`` (the narrow projection of
``QARecordV1`` that ships to the reader). Fields dropped on projection:
``schema_version``, ``document_id``, ``expected``, ``actual``, ``auto_fix``,
``evidence_refs``, ``waiver_ref``. These are internal provenance / fixer
state that the static dashboard and page badges never read.

The internal ``QARecordV1`` artifact is still written to the pipeline
artifact store with all fields intact — only the published bundle is
projected.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1


class PublicQARecordV1(BaseModel):
    """Public-facing single QA finding."""

    model_config = ConfigDict(extra="forbid")

    qa_id: str
    layer: QALayer
    severity: Severity
    code: str
    page_id: str | None = None
    entity_ref: str | None = None
    message: str = ""
    waived: bool = False

    @classmethod
    def from_internal(cls, internal: QARecordV1) -> PublicQARecordV1:
        """Project an internal ``QARecordV1`` to the public shape."""
        return cls(
            qa_id=internal.qa_id,
            layer=internal.layer,
            severity=internal.severity,
            code=internal.code,
            page_id=internal.page_id,
            entity_ref=internal.entity_ref,
            message=internal.message,
            waived=internal.waived,
        )


class PublicQARecordSetV1(BaseModel):
    """Public-facing QA record list written to ``<edition>/data/qa_records.json``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="public_qa_record_set.v1", pattern=r"^public_qa_record_set\.v\d+$"
    )
    records: list[PublicQARecordV1] = Field(default_factory=list)

    @classmethod
    def from_internal(cls, internals: list[QARecordV1]) -> PublicQARecordSetV1:
        """Build a projection from the list of internal records."""
        return cls(records=[PublicQARecordV1.from_internal(r) for r in internals])
