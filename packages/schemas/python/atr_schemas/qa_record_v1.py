"""QARecordV1 — individual machine-readable QA finding."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from atr_schemas.enums import QALayer, Severity


class AutoFix(BaseModel):
    """Available auto-fix for a QA issue."""

    available: bool = False
    fixer: str = ""


class QARecordV1(BaseModel):
    """A single QA finding."""

    schema_version: str = Field(default="qa_record.v1", pattern=r"^qa_record\.v\d+$")
    qa_id: str
    layer: QALayer
    severity: Severity
    code: str
    document_id: str = ""
    page_id: str | None = None
    entity_ref: str | None = None
    message: str = ""
    expected: Any = None
    actual: Any = None
    auto_fix: AutoFix | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    waived: bool = False
    waiver_ref: str | None = None
