"""Contract roundtrip tests for IconInline with anchor_kind/confidence fields."""

import json

from atr_schemas.common import Rect
from atr_schemas.enums import SymbolAnchorKind
from atr_schemas.page_ir_v1 import IconInline
from atr_schemas.resolved_page_v1 import ResolvedPageV1, ResolvedSymbolRef, SemanticConfidence


def _roundtrip(model_instance: object) -> None:
    model_cls = type(model_instance)
    json_str = model_cls.model_validate(model_instance).model_dump_json()
    parsed = json.loads(json_str)
    restored = model_cls.model_validate(parsed)
    assert restored == model_instance


def test_icon_inline_with_anchor_kind() -> None:
    icon = IconInline(
        symbol_id="sym.shield",
        instance_id="sym.shield.001",
        bbox=Rect(x0=10.0, y0=20.0, x1=22.0, y1=32.0),
        anchor_kind=SymbolAnchorKind.INLINE,
        confidence=0.92,
    )
    _roundtrip(icon)


def test_icon_inline_without_anchor_kind() -> None:
    """Backward compat: anchor_kind=None, confidence=1.0 (defaults)."""
    icon = IconInline(
        symbol_id="sym.arrow",
        instance_id="sym.arrow.001",
    )
    _roundtrip(icon)
    assert icon.anchor_kind is None
    assert icon.confidence == 1.0


def test_icon_inline_prefix_anchor() -> None:
    icon = IconInline(
        symbol_id="sym.bullet",
        anchor_kind=SymbolAnchorKind.PREFIX,
        confidence=0.85,
    )
    _roundtrip(icon)


def test_resolved_page_with_symbol_refs() -> None:
    ref = ResolvedSymbolRef(
        symbol_id="sym.shield",
        instance_id="sym.shield.001",
        anchor_kind=SymbolAnchorKind.INLINE,
        evidence_ids=["e.img.001"],
        bbox=Rect(x0=10.0, y0=20.0, x1=22.0, y1=32.0),
        confidence=0.95,
    )
    page = ResolvedPageV1(
        document_id="test-doc",
        page_id="p0001",
        page_number=1,
        symbol_refs=[ref],
        confidence=SemanticConfidence(symbol_resolution=0.95),
    )
    _roundtrip(page)
    assert len(page.symbol_refs) == 1
    assert page.symbol_refs[0].anchor_kind == SymbolAnchorKind.INLINE
