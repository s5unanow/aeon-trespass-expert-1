"""Typed configuration models for the ATR pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atr_schemas.common import Rect

# Translation provider canonical names — known to the config layer.
# A name listed here is *accepted* by Pydantic validation; the factory may
# still reject it (e.g. ``codex-cli`` is reserved here so configs can be
# authored against S5U-746 ahead of the S5U-747 adapter landing, but the
# factory raises until that adapter is wired up).
_KNOWN_TRANSLATION_PROVIDERS: frozenset[str] = frozenset(
    {"mock", "openai", "anthropic", "gemini", "gemini-cli", "codex-cli", "agy-cli"},
)

# Providers for which an empty ``model_default`` is acceptable because the
# adapter applies a documented default model (currently the Gemini family).
_PROVIDERS_WITH_DEFAULT_MODEL: frozenset[str] = frozenset({"gemini", "gemini-cli"})

# Providers that do not require a model at all (mock has no real call).
_PROVIDERS_WITHOUT_MODEL: frozenset[str] = frozenset({"mock"})


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


class CLIProviderOptions(BaseModel):
    """Options applicable to CLI-shaped providers (gemini-cli, codex-cli, agy-cli).

    Each field is optional — the adapter applies its own documented default
    when a value is omitted. Unknown keys are rejected (``extra="forbid"``)
    so a typo in TOML surfaces at config-load time, not at runtime.
    """

    model_config = ConfigDict(extra="forbid")

    executable: str | None = None
    """Override the path to the CLI binary. ``None`` -> rely on PATH."""

    timeout_seconds: int = Field(default=300, ge=1)
    """Subprocess timeout (seconds). Adapter must enforce this."""

    reasoning_effort: str | None = None
    """CLI reasoning-effort/profile value. Forwarded to codex-cli where it
    is a real flag; embedded in agy-cli prompts because AGY v1 exposes no
    model/effort flag. Ignored by gemini-cli."""

    sandbox: str | None = None
    """Codex CLI sandbox mode. Ignored by gemini-cli."""

    approval_policy: str | None = None
    """Codex CLI approval policy. Ignored by gemini-cli."""

    json_mode: bool = True
    """Require JSON-shaped output from the CLI (default true)."""

    output_file_mode: bool = False
    """If true, the adapter passes ``-o <path>`` and reads the file rather
    than capturing stdout. Codex CLI feature; gemini-cli ignores this."""


class APIProviderOptions(BaseModel):
    """Options applicable to API-shaped providers (openai, anthropic, gemini)."""

    model_config = ConfigDict(extra="forbid")

    api_key: str = ""
    """Provider API key. Empty -> rely on the SDK's environment fallback."""


class TranslationProviderOptions(BaseModel):
    """Provider-specific options bundle, namespaced by provider shape.

    ``cli`` carries options for CLI providers (gemini-cli, codex-cli).
    ``api`` carries options for API providers (openai, anthropic, gemini).
    Both are optional; default-empty namespaces are non-leakage and accepted
    by every provider. The factory enforces "options bundle matches provider
    shape" for *non-default* values (S5U-746).
    """

    model_config = ConfigDict(extra="forbid")

    cli: CLIProviderOptions = Field(default_factory=CLIProviderOptions)
    api: APIProviderOptions = Field(default_factory=APIProviderOptions)


class TranslationConfig(BaseModel):
    """Translation provider and model configuration.

    The flat ``provider`` / ``model_default`` / ``fallback_provider`` /
    ``fallback_model`` / ``temperature`` / ``max_retries`` /
    ``retry_delay_seconds`` keys remain the supported authoring surface. The
    nested ``provider_options`` / ``fallback_options`` namespaces carry
    provider-specific knobs without leaking across providers (S5U-746).
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = "gemini-cli"
    model_default: str = "gemini-2.5-flash"
    model_hard: str = "gemini-2.5-flash"
    fallback_provider: str = "gemini"
    fallback_model: str = "gemini-2.5-flash"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    batch_size: int = Field(default=24, ge=1)
    prompt_profile: str = "translate_rules_ru.v1"
    max_retries: int = Field(default=2, ge=0)
    retry_delay_seconds: float = Field(default=1.0, ge=0.0)

    provider_options: TranslationProviderOptions = Field(
        default_factory=TranslationProviderOptions,
    )
    fallback_options: TranslationProviderOptions = Field(
        default_factory=TranslationProviderOptions,
    )

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> TranslationConfig:
        # Normalize provider names to lower-case so casing differences
        # (``Codex-CLI``, ``GEMINI-CLI``) become non-issues downstream.
        object.__setattr__(self, "provider", self.provider.lower())
        if self.fallback_provider:
            object.__setattr__(
                self,
                "fallback_provider",
                self.fallback_provider.lower(),
            )

        # Reject unknown provider names early — before any LLM/subprocess
        # call. The factory may further reject reserved names (e.g.
        # ``codex-cli`` until its adapter lands) but this layer is the
        # strict allowlist gate for the config surface.
        if self.provider not in _KNOWN_TRANSLATION_PROVIDERS:
            msg = (
                f"Unknown translation provider: {self.provider!r}. "
                f"Known providers: {sorted(_KNOWN_TRANSLATION_PROVIDERS)}"
            )
            raise ValueError(msg)
        if self.fallback_provider and self.fallback_provider not in _KNOWN_TRANSLATION_PROVIDERS:
            msg = (
                f"Unknown translation fallback_provider: "
                f"{self.fallback_provider!r}. "
                f"Known providers: {sorted(_KNOWN_TRANSLATION_PROVIDERS)}"
            )
            raise ValueError(msg)

        # Require ``model_default`` for non-mock, non-Gemini-family providers.
        # Gemini-family adapters apply a documented default when the field
        # is empty; mock has no real call. Anything else is a config bug.
        if (
            self.provider not in _PROVIDERS_WITHOUT_MODEL
            and self.provider not in _PROVIDERS_WITH_DEFAULT_MODEL
            and not self.model_default
        ):
            msg = (
                f"Provider {self.provider!r} requires a non-empty "
                f"model_default — no documented default exists for this "
                f"provider."
            )
            raise ValueError(msg)
        if (
            self.fallback_provider
            and self.fallback_provider not in _PROVIDERS_WITHOUT_MODEL
            and self.fallback_provider not in _PROVIDERS_WITH_DEFAULT_MODEL
            and not self.fallback_model
        ):
            msg = (
                f"Fallback provider {self.fallback_provider!r} requires a "
                f"non-empty fallback_model — no documented default exists "
                f"for this provider."
            )
            raise ValueError(msg)

        return self


class StructurePageOverride(BaseModel):
    """Per-page structure override — for pages where automatic detection fails."""

    table_regions: list[Rect] = Field(default_factory=list)


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

    # S5U-698 — refuse multi-cell heading merges. When three or more
    # heading-classified spans sit on the same y-baseline separated by gaps
    # wider than this threshold, the line is treated as a multi-column table
    # header row (e.g. p0054 "Wounded card: | BP deck | AI deck") rather than
    # a single HeadingBlock. The default is chosen well above typical word-gap
    # sizes (<10pt) and above heading kerning (~20pt), so legitimate
    # single-column headings are preserved.
    heading_cell_split_gap_pt: float = Field(default=40.0, gt=0.0)

    # S5U-704 — split a table-body row's spans into cells when horizontal
    # gaps exceed this threshold. Tuned lower than
    # ``heading_cell_split_gap_pt`` because body cells are usually tighter
    # and narrower-gapped than the emphatic header row. ~25 pt catches the
    # three-column ATO rulebook chart body (BP | BP deck action | AI deck
    # action) without splitting normal prose spans.
    table_body_cell_split_gap_pt: float = Field(default=25.0, gt=0.0)

    # Per-page structure overrides
    page_overrides: dict[str, StructurePageOverride] = Field(default_factory=dict)

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
    facsimile_annotation_keep_texts: list[str] | None = None


class RenderConfig(BaseModel):
    """Render stage configuration."""

    facsimile_coverage_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    annotation_max_bbox_area: float = Field(default=0.10, ge=0.0, le=1.0)
    annotation_max_total_area: float = Field(default=0.30, ge=0.0)
    # S5U-697 Codex round-3: cap at 99 so inactive-marker z-index (1 + stackRank)
    # never collides with the reader's tooltip layer (z-index 100). If a future
    # page genuinely needs more hotspots, raise the cap AND bump the tooltip
    # z-index in apps/web/src/styles/reader.css to preserve the invariant.
    annotation_max_count: int = Field(default=25, ge=0, le=99)
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
