"""ReviewPackV1 — bundled QA findings for human review."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.waiver_v1 import WaiverV1


class ReviewFinding(BaseModel):
    """A single finding with its waiver template."""

    record: QARecordV1
    waiver_template: WaiverV1


class ReviewPackV1(BaseModel):
    """Human-reviewable bundle of blocking/ambiguous QA findings.

    Contains all unwaived blocking findings grouped by page,
    plus pre-filled waiver templates that a reviewer can approve.
    """

    schema_version: str = Field(
        default="review_pack.v1",
        pattern=r"^review_pack\.v\d+$",
    )
    document_id: str
    run_id: str = ""
    total_findings: int = 0
    blocking_findings: int = 0
    waived_findings: int = 0
    findings: list[ReviewFinding] = Field(default_factory=list)
