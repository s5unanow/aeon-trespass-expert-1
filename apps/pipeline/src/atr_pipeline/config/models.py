"""Typed configuration models for the ATR pipeline."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class DocumentConfig(BaseModel):
    """Document-specific configuration."""

    id: str
    source_pdf: str
    source_lang: str = "en"
    target_langs: list[str] = Field(default_factory=lambda: ["ru"])


class PipelineConfig(BaseModel):
    """Pipeline execution configuration."""

    version: str = "0.1.0"
    parallelism: int = Field(default=4, ge=1)
    review_threshold: float = Field(default=0.80, ge=0.0, le=1.0)


class ExtractNativeConfig(BaseModel):
    """Native extraction configuration."""

    engine: str = "pymupdf"


class ExtractLayoutConfig(BaseModel):
    """Layout extraction configuration."""

    primary: str = "docling"
    hard_fallback: str = "paddleocr"
    dpi: int = Field(default=300, ge=72)


class ExtractionConfig(BaseModel):
    """Combined extraction configuration."""

    native: ExtractNativeConfig = Field(default_factory=ExtractNativeConfig)
    layout: ExtractLayoutConfig = Field(default_factory=ExtractLayoutConfig)


class SymbolsConfig(BaseModel):
    """Symbol catalog and matching configuration."""

    catalog: str = ""
    match_threshold: float = Field(default=0.93, ge=0.0, le=1.0)


class TranslationConfig(BaseModel):
    """Translation provider and model configuration."""

    provider: str = "openai"
    model_default: str = "gpt-4o"
    model_hard: str = "gpt-4o"
    fallback_provider: str = "anthropic"
    fallback_model: str = "claude-sonnet-4-6"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    batch_size: int = Field(default=24, ge=1)
    prompt_profile: str = "translate_rules_ru.v1"


class QAConfig(BaseModel):
    """QA gate configuration."""

    block_publish_on: list[str] = Field(default_factory=lambda: ["error", "critical"])


class DocumentBuildConfig(BaseModel):
    """Full resolved configuration for building a document."""

    document: DocumentConfig
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    symbols: SymbolsConfig = Field(default_factory=SymbolsConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    qa: QAConfig = Field(default_factory=QAConfig)

    # Resolved paths (set by loader)
    repo_root: Path = Field(default=Path("."))
    artifact_root: Path = Field(default=Path("artifacts"))

    @property
    def source_pdf_path(self) -> Path:
        """Resolved path to source PDF."""
        p = Path(self.document.source_pdf)
        if p.is_absolute():
            return p
        return self.repo_root / p

    @property
    def symbol_catalog_path(self) -> Path | None:
        """Resolved path to symbol catalog, if configured."""
        if not self.symbols.catalog:
            return None
        p = Path(self.symbols.catalog)
        if p.is_absolute():
            return p
        return self.repo_root / p
