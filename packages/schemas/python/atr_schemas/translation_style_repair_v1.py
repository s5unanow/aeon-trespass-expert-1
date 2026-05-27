"""TranslationStyleRepairV1 — targeted Russian paragraph repair report."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TranslationStyleRepairChangeV1(BaseModel):
    """One paragraph changed by the targeted style repair stage."""

    model_config = ConfigDict(extra="forbid")

    paragraph_id: str = Field(min_length=1)
    block_type: str = ""
    before_text: str
    after_text: str
    finding_quotes: list[str] = Field(default_factory=list)
    diff: list[str] = Field(default_factory=list)


class TranslationStyleRepairPageV1(BaseModel):
    """Per-page report for targeted Russian paragraph repair."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="translation_style_repair.v1",
        pattern=r"^translation_style_repair\.v\d+$",
    )
    document_id: str
    page_id: str
    source_critic_findings_count: int = Field(ge=0)
    repaired_paragraph_ids: list[str] = Field(default_factory=list)
    skipped_paragraph_ids: list[str] = Field(default_factory=list)
    changes: list[TranslationStyleRepairChangeV1] = Field(default_factory=list)
    post_repair_translation_qa_count: int = Field(ge=0, default=0)
    post_repair_style_qa_count: int = Field(ge=0, default=0)
