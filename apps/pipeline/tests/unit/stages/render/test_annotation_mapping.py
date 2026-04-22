"""Tests for facsimile annotation mapping & overlay collision safeguards.

Covers the S5U-697 fix class: wrong EN↔RU pairings caused by stale RU IR,
fully-occluded hotspots, and non-finite bboxes. These checks live alongside
the pre-existing quality filters in ``annotation_builder.py`` and are kept
in a separate test module so the grandfathered
``test_annotation_builder.py`` does not grow past its frozen line count.
"""

from __future__ import annotations

from atr_pipeline.stages.render.annotation_builder import (
    AnnotationQualityConfig,
    build_facsimile_annotations,
)
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import PageIRV1, ParagraphBlock, TextInline


def _mk_en(blocks: list) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id="p0007",
        page_number=7,
        language=LanguageCode.EN,
        dimensions_pt=PageDimensions(width=612.0, height=792.0),
        blocks=blocks,
    )


def _mk_ru(blocks: list) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id="p0007",
        page_number=7,
        language=LanguageCode.RU,
        dimensions_pt=PageDimensions(width=612.0, height=792.0),
        blocks=blocks,
    )


def _para(bid: str, bbox: Rect, text: str) -> ParagraphBlock:
    return ParagraphBlock(
        block_id=bid,
        bbox=bbox,
        children=[TextInline(text=text)],
    )


# ---------------------------------------------------------------------------
# Stale-pairing detection (issue: "stale cached annotation payloads")
# ---------------------------------------------------------------------------


def test_drops_ru_translation_when_length_is_implausibly_large() -> None:
    """RU text whose character length is >5x the EN text is rejected as a bad pairing.

    Mirrors the observed p0007 failure mode where block_id
    `p0007.b016` (EN "170 Secret Cards", 16 chars) was paired with a
    multi-paragraph RU blob of ~200+ chars due to a stale RU IR.
    """
    en = _mk_en(
        [
            _para("p0007.b001", Rect(x0=10, y0=10, x1=100, y1=30), "170 Secret Cards"),
        ]
    )
    long_ru_blob = (
        "Отбрасывание 2. Вы уничтожили слабую опорную руку, изрешеченную "
        "осколками сиреневой раковины. Монстр остался полностью открытым! "
        "Во время второго окна способностей поместите 2 дополнительных жетона "
        "Открытия или Прорыва в пул Кратоса."
    )
    ru = _mk_ru(
        [
            _para("p0007.b001", Rect(x0=10, y0=10, x1=100, y1=30), long_ru_blob),
        ]
    )
    # Permissive quality config so only the new pairing filter matters here.
    cfg = AnnotationQualityConfig(
        max_bbox_area=1.0,
        max_total_area=2.0,
        max_drop_ratio=1.0,
        min_letter_ratio=0.1,
    )
    result = build_facsimile_annotations(en, ru, quality=cfg)

    assert len(result) == 1, "EN annotation should survive without the stale RU translation"
    assert result[0].text == "170 Secret Cards"
    assert result[0].translated_text == "", (
        "Stale RU translation must be dropped; tooltip should fall back to EN text only"
    )


def test_drops_ru_translation_when_length_is_implausibly_small() -> None:
    """RU text whose character length is <0.2x the EN text is rejected.

    Mirrors the observed p0007 failure where EN "20 Divider Cards" was
    paired with RU "?".
    """
    en = _mk_en(
        [
            _para(
                "p0007.b001",
                Rect(x0=10, y0=10, x1=200, y1=30),
                "This is a fairly long English paragraph about components.",
            ),
        ]
    )
    ru = _mk_ru([_para("p0007.b001", Rect(x0=10, y0=10, x1=200, y1=30), "?")])
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    result = build_facsimile_annotations(en, ru, quality=cfg)

    assert len(result) == 1
    assert result[0].translated_text == ""


def test_legitimate_translation_pair_is_preserved() -> None:
    """Clean EN→RU pair with plausible length ratio stays intact.

    Regression check against over-filtering.
    """
    en = _mk_en(
        [
            _para(
                "p0007.b001",
                Rect(x0=10, y0=10, x1=200, y1=30),
                "This page shows game components.",
            ),
        ]
    )
    ru = _mk_ru(
        [
            _para(
                "p0007.b001",
                Rect(x0=10, y0=10, x1=200, y1=30),
                "На этой странице показаны игровые компоненты.",
            ),
        ]
    )
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    result = build_facsimile_annotations(en, ru, quality=cfg)

    assert len(result) == 1
    assert result[0].translated_text.startswith("На этой странице")


def test_page_level_staleness_clears_all_translations() -> None:
    """When >=30% of paired EN/RU blocks fail the length ratio check, every
    translation on the page is cleared — the RU IR is treated as stale.

    Captures the ``199 BP Cards`` ↔ ``12 Первозданных Листов`` p0007 case
    where individual pairs pass the per-annotation length check yet the
    page as a whole is clearly mis-aligned because many block_ids pair
    with wildly disproportionate RU text from a shuffled index.
    """
    en = _mk_en(
        [
            _para("p0007.b001", Rect(x0=10, y0=10, x1=100, y1=30), "199 BP Cards"),
            _para("p0007.b002", Rect(x0=10, y0=40, x1=100, y1=60), "170 Secret Cards"),
            _para("p0007.b003", Rect(x0=10, y0=70, x1=100, y1=90), "20 Divider Cards"),
            _para("p0007.b004", Rect(x0=10, y0=100, x1=100, y1=120), "8 Moiros Cards"),
        ]
    )
    # 2 of 4 pairings are egregiously wrong (>5x ratio); the other 2 are
    # length-plausible but still from a shuffled RU IR. The page-level
    # staleness escalation must clear *all* translated_text values.
    ru = _mk_ru(
        [
            _para(
                "p0007.b001",
                Rect(x0=10, y0=10, x1=100, y1=30),
                "Отбрасывание 2. Вы уничтожили слабую опорную руку, изрешеченную "
                "осколками сиреневой раковины. Монстр остался полностью открытым!",
            ),  # huge — fails per-ann check
            _para("p0007.b002", Rect(x0=10, y0=40, x1=100, y1=60), "7-9"),  # tiny — fails
            _para(
                "p0007.b003", Rect(x0=10, y0=70, x1=100, y1=90), "199 БП Карт 10 Карт Черты"
            ),  # length-plausible but semantically wrong
            _para(
                "p0007.b004",
                Rect(x0=10, y0=100, x1=100, y1=120),
                "27 Карт Шаблонов 1-3",
            ),  # length-plausible but semantically wrong
        ]
    )
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0, max_drop_ratio=1.0)
    result = build_facsimile_annotations(en, ru, quality=cfg)

    assert len(result) == 4, "All EN annotations should survive (empty RU)"
    for ann in result:
        assert ann.translated_text == "", (
            f"Page-level staleness should have cleared translated_text, got {ann.translated_text!r}"
        )


def test_page_without_staleness_keeps_translations() -> None:
    """Regression: when most pairings are plausible, individual translations
    are preserved even if one is implausible."""
    en = _mk_en(
        [
            _para(
                "p0007.b001",
                Rect(x0=10, y0=10, x1=200, y1=30),
                "This page shows game components.",
            ),
            _para(
                "p0007.b002",
                Rect(x0=10, y0=40, x1=200, y1=60),
                "Figure 1: Token layout",
            ),
            _para(
                "p0007.b003",
                Rect(x0=10, y0=70, x1=200, y1=90),
                "Real text number three",
            ),
            _para("p0007.b004", Rect(x0=10, y0=100, x1=200, y1=120), "Short"),
        ]
    )
    ru = _mk_ru(
        [
            _para(
                "p0007.b001",
                Rect(x0=10, y0=10, x1=200, y1=30),
                "На этой странице показаны игровые компоненты.",
            ),
            _para(
                "p0007.b002",
                Rect(x0=10, y0=40, x1=200, y1=60),
                "Рисунок 1: жетоны",
            ),
            _para(
                "p0007.b003",
                Rect(x0=10, y0=70, x1=200, y1=90),
                "Реальный текст номер три",
            ),
            # Only this one is implausible (>5x) — 1 of 4 pairs = 25% < 30%
            _para(
                "p0007.b004",
                Rect(x0=10, y0=100, x1=200, y1=120),
                "Сильно большая строка которая намного длиннее исходника",
            ),
        ]
    )
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    result = build_facsimile_annotations(en, ru, quality=cfg)

    by_text = {a.text: a.translated_text for a in result}
    # Plausible pairs keep their translations
    assert by_text["This page shows game components."].startswith("На этой странице")
    assert by_text["Figure 1: Token layout"].startswith("Рисунок")
    # The individually-bad pair has its translation cleared
    assert by_text["Short"] == ""


# ---------------------------------------------------------------------------
# Overlay collision suppression (issue: "fully occludes another hotspot")
# ---------------------------------------------------------------------------


def test_drops_outer_annotation_when_one_fully_contains_another() -> None:
    """When bbox A fully contains bbox B, only B survives (inner is specific)."""
    en = _mk_en(
        [
            _para("p0007.b001", Rect(x0=0, y0=0, x1=300, y1=300), "Outer large block"),
            _para("p0007.b002", Rect(x0=50, y0=50, x1=100, y1=100), "Inner small block"),
        ]
    )
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    result = build_facsimile_annotations(en, quality=cfg)

    texts = {a.text for a in result}
    assert "Inner small block" in texts, "Inner hotspot must remain reachable"
    assert "Outer large block" not in texts, (
        "Outer hotspot that fully occludes another must be suppressed"
    )


def test_sibling_annotations_with_disjoint_bboxes_both_survive() -> None:
    """Regression: disjoint bboxes are not affected by the occlusion filter."""
    en = _mk_en(
        [
            _para("p0007.b001", Rect(x0=10, y0=10, x1=100, y1=50), "Left block"),
            _para("p0007.b002", Rect(x0=200, y0=200, x1=300, y1=240), "Right block"),
        ]
    )
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    result = build_facsimile_annotations(en, quality=cfg)

    assert len(result) == 2


def test_partial_overlap_does_not_trigger_suppression() -> None:
    """Overlapping but not-containing bboxes are both kept."""
    en = _mk_en(
        [
            _para("p0007.b001", Rect(x0=10, y0=10, x1=100, y1=50), "A"),
            _para("p0007.b002", Rect(x0=80, y0=30, x1=150, y1=70), "B"),
        ]
    )
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    result = build_facsimile_annotations(en, quality=cfg)

    assert len(result) == 2


def test_multi_occlusion_does_not_trip_drop_ratio_gate() -> None:
    """Multiple legitimately-redundant nested hotspots must not blow the
    drop-ratio gate to []: occlusion suppression is a deduplication, not a
    quality rejection. Codex round-2 review finding.
    """
    # 4 concentric-ish outer blocks around one small inner block. Each
    # outer strictly contains the inner, so _suppress_fully_occluded drops
    # all 4 outers. With default max_drop_ratio=0.5, a naive candidate
    # count of 5 would see 4 drops / 5 = 80% → page suppressed.
    en = _mk_en(
        [
            _para("p0007.b001", Rect(x0=0, y0=0, x1=200, y1=200), "Huge outer"),
            _para("p0007.b002", Rect(x0=20, y0=20, x1=180, y1=180), "Less huge outer"),
            _para("p0007.b003", Rect(x0=40, y0=40, x1=160, y1=160), "Medium outer"),
            _para("p0007.b004", Rect(x0=60, y0=60, x1=140, y1=140), "Small outer"),
            _para("p0007.b005", Rect(x0=90, y0=90, x1=110, y1=110), "Inner target"),
        ]
    )
    # Permissive bbox area so the outer blocks are not already dropped by
    # the per-annotation area filter; the drop-ratio gate is the one the
    # test is exercising.
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0, max_drop_ratio=0.5)
    result = build_facsimile_annotations(en, quality=cfg)
    texts = {a.text for a in result}
    assert "Inner target" in texts, (
        f"Inner hotspot should survive occlusion deduplication; got {texts}"
    )


# ---------------------------------------------------------------------------
# Bbox validity (issue: "non-finite bbox coordinates")
# ---------------------------------------------------------------------------


def test_degenerate_bbox_is_dropped() -> None:
    """Zero-area bboxes (x1<=x0 or y1<=y0 after normalization) are dropped."""
    en = _mk_en(
        [
            # Collapsed-width bbox: x1 == x0 after normalization → zero area
            _para("p0007.b001", Rect(x0=50, y0=10, x1=50, y1=50), "Collapsed bbox"),
            _para("p0007.b002", Rect(x0=10, y0=100, x1=100, y1=140), "Valid bbox"),
        ]
    )
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0)
    result = build_facsimile_annotations(en, quality=cfg)

    texts = {a.text for a in result}
    assert "Valid bbox" in texts
    assert "Collapsed bbox" not in texts, "Degenerate bbox must be rejected"


def test_non_finite_bbox_coords_are_dropped_before_normalization() -> None:
    """NaN / +Inf / -Inf in raw bbox coords are rejected pre-clamp.

    Closes the defect Codex caught in the first review pass: Python's
    `min(1.0, nan)` is 1.0, so a post-normalization finite-check would
    let a corrupted extractor bbox through as a valid-looking [0,1]
    rectangle.
    """
    import math as _math

    en_blocks = []
    for i, (x0, y0, x1, y1) in enumerate(
        [
            (_math.nan, 10, 100, 30),
            (10, _math.inf, 100, 30),
            (-_math.inf, 10, 100, 30),
            (10, 10, _math.nan, 30),
            (10, 10, 100, _math.inf),
        ]
    ):
        en_blocks.append(_para(f"p0007.b{i:03d}", Rect(x0=x0, y0=y0, x1=x1, y1=y1), f"Corrupt {i}"))
    # One valid block to prove the rest of the pipeline still produces output.
    en_blocks.append(_para("p0007.b999", Rect(x0=10, y0=10, x1=100, y1=30), "Valid control"))
    en = _mk_en(en_blocks)
    # Permissive max_drop_ratio so the page is not suppressed for dropping
    # the 5 corrupted blocks — the assertion is on the *set* of survivors.
    cfg = AnnotationQualityConfig(max_bbox_area=1.0, max_total_area=2.0, max_drop_ratio=1.0)
    result = build_facsimile_annotations(en, quality=cfg)

    texts = {a.text for a in result}
    assert texts == {"Valid control"}, (
        f"Only the valid control block should survive non-finite rejection, got {texts}"
    )
    # Belt-and-suspenders: every surviving bbox has finite coords.
    for ann in result:
        assert all(_math.isfinite(c) for c in (ann.bbox.x0, ann.bbox.y0, ann.bbox.x1, ann.bbox.y1))
