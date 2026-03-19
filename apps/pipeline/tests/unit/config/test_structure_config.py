"""Tests for StructureConfig model defaults and validation."""

import pytest
from pydantic import ValidationError

from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig, StructureConfig


def test_structure_config_defaults_match_hardcoded_values() -> None:
    """All defaults must match the original hardcoded constants in real_block_builder."""
    cfg = StructureConfig()

    # Font classification
    assert cfg.heading_fonts == frozenset({"GreenleafLightPro", "Goobascript"})
    assert cfg.decorative_fonts == frozenset({"GreenleafBannersRegularL"})
    assert cfg.body_font == "Adonis-Regular"
    assert cfg.bold_font == "Adonis-Bold"
    assert cfg.italic_font == "Adonis-Italic"
    assert cfg.bold_italic_font == "Adonis-BoldItalic"
    assert cfg.dingbat_font == "ITCZapfDingbatsMedium"

    # Layout thresholds
    assert cfg.footer_y_threshold == 790.0
    assert cfg.heading_min_size == 8.0
    assert cfg.subheading_bold_min_size == 10.0
    assert cfg.body_size_min == 7.5
    assert cfg.body_size_max == 10.0

    # Paragraph splitting
    assert cfg.paragraph_gap_factor == 1.5
    assert cfg.paragraph_gap_abs == 12.0

    # Figure promotion
    assert cfg.figure_min_width_pt == 100.0
    assert cfg.figure_min_height_pt == 100.0


def test_structure_config_overrides() -> None:
    """Values can be overridden from config."""
    cfg = StructureConfig(
        heading_fonts=frozenset({"CustomFont"}),
        footer_y_threshold=800.0,
        paragraph_gap_factor=2.0,
    )
    assert cfg.heading_fonts == frozenset({"CustomFont"})
    assert cfg.footer_y_threshold == 800.0
    assert cfg.paragraph_gap_factor == 2.0
    # Unset fields keep defaults
    assert cfg.body_font == "Adonis-Regular"


def test_structure_config_in_document_build_config() -> None:
    """StructureConfig is accessible on DocumentBuildConfig with defaults."""
    doc_cfg = DocumentConfig(id="test", source_pdf="test.pdf")
    build_cfg = DocumentBuildConfig(document=doc_cfg)
    assert isinstance(build_cfg.structure, StructureConfig)
    assert build_cfg.structure.footer_y_threshold == 790.0


def test_structure_config_rejects_negative_sizes() -> None:
    """Physical dimension fields must be non-negative."""
    with pytest.raises(ValidationError):
        StructureConfig(heading_min_size=-1.0)
    with pytest.raises(ValidationError):
        StructureConfig(figure_min_width_pt=-10.0)


def test_structure_config_rejects_inverted_body_size_range() -> None:
    """body_size_min must be <= body_size_max."""
    with pytest.raises(ValidationError, match="body_size_min"):
        StructureConfig(body_size_min=12.0, body_size_max=8.0)


def test_structure_config_rejects_zero_gap_factor() -> None:
    """Gap factor must be strictly positive."""
    with pytest.raises(ValidationError):
        StructureConfig(paragraph_gap_factor=0.0)
