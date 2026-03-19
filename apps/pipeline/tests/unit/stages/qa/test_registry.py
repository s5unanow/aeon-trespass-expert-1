"""Tests for the QA rule registry."""

from __future__ import annotations

from atr_pipeline.stages.qa.registry import (
    DecorativeIconRule,
    GluedTextRule,
    IconCountRule,
    LeakedIdentifierRule,
    QAPageContext,
    QARule,
    get_all_rules,
)
from atr_schemas.enums import LanguageCode, QALayer
from atr_schemas.page_ir_v1 import PageIRV1, ParagraphBlock, TextInline
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def _make_ir() -> PageIRV1:
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[ParagraphBlock(block_id="b1", children=[TextInline(text="Hello")])],
    )


def _make_render() -> RenderPageV1:
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", title="Test", source_page_number=1),
        blocks=[RenderParagraphBlock(id="b1", children=[RenderTextInline(text="Hello")])],
        source_map=RenderSourceMap(page_id="p0001", block_refs=[]),
    )


def _make_ctx() -> QAPageContext:
    return QAPageContext(source_ir=_make_ir(), target_ir=_make_ir(), render_page=_make_render())


def test_get_all_rules_returns_all_four() -> None:
    rules = get_all_rules()
    assert len(rules) == 4


def test_get_all_rules_unique_names() -> None:
    rules = get_all_rules()
    names = [r.name for r in rules]
    assert len(names) == len(set(names))


def test_all_rules_satisfy_protocol() -> None:
    for rule in get_all_rules():
        assert isinstance(rule.name, str)
        assert isinstance(rule.layer, QALayer)
        # Protocol structural check: evaluate must be callable
        assert callable(rule.evaluate)


def test_icon_count_rule_properties() -> None:
    rule = IconCountRule()
    assert rule.name == "icon_count"
    assert rule.layer == QALayer.ICON_SYMBOL


def test_decorative_icon_rule_properties() -> None:
    rule = DecorativeIconRule()
    assert rule.name == "decorative_icon"
    assert rule.layer == QALayer.RENDER


def test_glued_text_rule_properties() -> None:
    rule = GluedTextRule()
    assert rule.name == "glued_text"
    assert rule.layer == QALayer.EXTRACTION


def test_leaked_identifier_rule_properties() -> None:
    rule = LeakedIdentifierRule()
    assert rule.name == "leaked_identifier"
    assert rule.layer == QALayer.RENDER


def test_rules_evaluate_clean_page() -> None:
    """All rules return empty lists on clean input."""
    ctx = _make_ctx()
    for rule in get_all_rules():
        records = rule.evaluate(ctx)
        assert records == [], f"{rule.name} returned unexpected records"


def _assert_is_qa_rule(rule: QARule) -> None:
    """Type-check helper — verifies structural compatibility with the protocol."""
    assert hasattr(rule, "name")
    assert hasattr(rule, "layer")
    assert hasattr(rule, "evaluate")


def test_each_rule_matches_protocol_structurally() -> None:
    for rule in get_all_rules():
        _assert_is_qa_rule(rule)
