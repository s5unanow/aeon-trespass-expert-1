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
    """Human-reviewable bundle of QA findings that need attention.

    Contains all unwaived findings whose severity is in ``block_on`` plus
    any unwaived ``QALayer.CONFIDENCE`` records with
    ``code=CONFIDENCE_QA_REQUIRED`` (surfaced for triage even though they
    do not by themselves block publishing). Each finding is paired with a
    pre-filled waiver template a reviewer can approve.
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
