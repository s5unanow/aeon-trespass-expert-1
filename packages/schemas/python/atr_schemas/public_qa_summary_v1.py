"""PublicQASummaryV1 — public-facing QA summary for the web bundle (S5U-689).

This is the narrow projection of ``QASummaryV1`` that ships to the static
reader. It intentionally omits internal artifact-store references and run
identifiers (``run_id``, ``record_refs``, ``review_pack_ref``,
``qa_metrics_ref``) — the reader only needs severity counts and the blocking
flag for the dashboard + page badges.

The internal ``QASummaryV1`` artifact is still written to the pipeline
artifact store with all fields intact — only the published bundle is
projected.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from atr_schemas.qa_summary_v1 import QASummaryV1, SeverityCounts


class PublicQASummaryV1(BaseModel):
    """Public-facing QA summary written to ``<edition>/data/qa_summary.json``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="public_qa_summary.v1", pattern=r"^public_qa_summary\.v\d+$"
    )
    document_id: str
    edition: str = ""
    counts: SeverityCounts = Field(default_factory=SeverityCounts)
    waived_counts: SeverityCounts = Field(default_factory=SeverityCounts)
    blocking: bool = False

    @classmethod
    def from_internal(cls, internal: QASummaryV1) -> PublicQASummaryV1:
        """Project an internal ``QASummaryV1`` to the public shape.

        The projection drops every internal field (``run_id``,
        ``record_refs``, ``review_pack_ref``, ``qa_metrics_ref``). Reader
        tests grep for these keys on the exported JSON; presence is a
        regression.
        """
        return cls(
            document_id=internal.document_id,
            edition=internal.edition,
            counts=internal.counts,
            waived_counts=internal.waived_counts,
            blocking=internal.blocking,
        )
