"""Typed configuration models for the ATR pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DocumentConfig(BaseModel):
    """Document-specific configuration."""

    id: str
    source_pdf: str
    source_lang: str = "en"
    target_langs: list[str] = Field(default_factory=lambda: ["ru"])
    structure_builder: Literal["real", "simple"] = "real"


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


class RasterConfig(BaseModel):
    """Raster rendering configuration — controls the per-page render pyramid."""

    pyramid_dpi: list[int] = Field(default_factory=lambda: [150, 300], min_length=1)

    @model_validator(mode="after")
    def _check_dpi_values(self) -> RasterConfig:
        for dpi in self.pyramid_dpi:
            if dpi < 72:
                msg = f"pyramid_dpi values must be >= 72, got {dpi}"
                raise ValueError(msg)
        return self


class ExtractionConfig(BaseModel):
    """Combined extraction configuration."""

    native: ExtractNativeConfig = Field(default_factory=ExtractNativeConfig)
    layout: ExtractLayoutConfig = Field(default_factory=ExtractLayoutConfig)
    raster: RasterConfig = Field(default_factory=RasterConfig)


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
    max_retries: int = Field(default=2, ge=0)
    retry_delay_seconds: float = Field(default=1.0, ge=0.0)


class StructureConfig(BaseModel):
    """Structure recovery constants — externalised from real_block_builder."""

    # Font classification
    heading_fonts: frozenset[str] = Field(
        default_factory=lambda: frozenset({"GreenleafLightPro", "Goobascript"}),
    )
    decorative_fonts: frozenset[str] = Field(
        default_factory=lambda: frozenset({"GreenleafBannersRegularL"}),
    )
    body_font: str = "Adonis-Regular"
    bold_font: str = "Adonis-Bold"
    italic_font: str = "Adonis-Italic"
    bold_italic_font: str = "Adonis-BoldItalic"
    dingbat_font: str = "ITCZapfDingbatsMedium"

    # Layout thresholds
    footer_y_threshold: float = 790.0
    heading_min_size: float = Field(default=8.0, ge=0.0)
    subheading_bold_min_size: float = Field(default=10.0, ge=0.0)
    body_size_min: float = Field(default=7.5, ge=0.0)
    body_size_max: float = Field(default=10.0, ge=0.0)

    # Paragraph splitting
    paragraph_gap_factor: float = Field(default=1.5, gt=0.0)
    paragraph_gap_abs: float = Field(default=12.0, gt=0.0)

    # Figure promotion
    figure_min_width_pt: float = Field(default=100.0, ge=0.0)
    figure_min_height_pt: float = Field(default=100.0, ge=0.0)

    # Region segmentation
    gutter_min_width_pt: float = Field(default=10.0, gt=0.0)
    full_width_fraction: float = Field(default=0.85, gt=0.0, le=1.0)
    band_gap_min_pt: float = Field(default=15.0, gt=0.0)
    furniture_top_max_y: float = Field(default=60.0, ge=0.0)
    furniture_bottom_min_y: float = Field(default=750.0, ge=0.0)
    margin_note_max_width_fraction: float = Field(default=0.20, gt=0.0, le=1.0)
    margin_note_edge_margin_pt: float = Field(default=40.0, ge=0.0)
    callout_max_width_fraction: float = Field(default=0.55, gt=0.0, le=1.0)

    # Semantic resolver
    caption_proximity_pt: float = Field(default=25.0, ge=0.0)
    caption_max_text_length: int = Field(default=200, ge=1)
    table_min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_body_size_range(self) -> StructureConfig:
        if self.body_size_min > self.body_size_max:
            msg = (
                f"body_size_min ({self.body_size_min}) must be "
                f"<= body_size_max ({self.body_size_max})"
            )
            raise ValueError(msg)
        return self


class PageOverride(BaseModel):
    """Per-page configuration override."""

    presentation_mode: Literal["article", "facsimile"] | None = None
    title: str | None = None
    facsimile_annotations: bool | None = None


class RenderConfig(BaseModel):
    """Render stage configuration."""

    facsimile_coverage_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    annotation_max_bbox_area: float = Field(default=0.10, ge=0.0, le=1.0)
    annotation_max_total_area: float = Field(default=0.30, ge=0.0)
    annotation_max_count: int = Field(default=25, ge=0)
    annotation_min_letter_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    annotation_max_drop_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    page_overrides: dict[str, PageOverride] = Field(default_factory=dict)


class QAConfig(BaseModel):
    """QA gate configuration."""

    block_publish_on: list[str] = Field(default_factory=lambda: ["error", "critical"])
    waivers_dir: str = "waivers"


class DocumentBuildConfig(BaseModel):
    """Full resolved configuration for building a document."""

    document: DocumentConfig
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    symbols: SymbolsConfig = Field(default_factory=SymbolsConfig)
    structure: StructureConfig = Field(default_factory=StructureConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
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
