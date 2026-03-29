"""Regression test: p0082 (symbol legend) must retain inline icon nodes.

This test reads the exported render-page JSON for p0082 and asserts that
gameplay symbols are present as icon nodes.  p0082 is the primary
diagnostic page for S5U-436 — it functions as a symbol legend and should
contain icon nodes for every entry rather than plain-text labels.

The test runs against the exported web data so it stays fast and does
not depend on the pipeline runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RENDER_FILE = (
    _REPO_ROOT
    / "apps"
    / "web"
    / "public"
    / "documents"
    / "ato_core_v1_1"
    / "en"
    / "data"
    / "render_page.p0082.json"
)

# Minimum icon count that p0082 must have (legend entries).
# The actual count is 15 as of the S5U-436 fix; a small margin
# allows for minor future changes without breaking this gate.
_MIN_ICON_COUNT = 12

# Symbols that must appear at least once on the legend page.
_REQUIRED_SYMBOLS = {
    "sym.danger",
    "sym.fate",
    "sym.rage",
    "sym.progress",
    "sym.doom",
    "sym.crew",
    "sym.hull",
    "sym.argo_fate",
    "sym.argo_knowledge",
}


@pytest.mark.skipif(not _RENDER_FILE.exists(), reason="exported render data not present")
def test_p0082_icon_count() -> None:
    """p0082 render page must contain at least _MIN_ICON_COUNT icon inlines."""
    data = json.loads(_RENDER_FILE.read_text())
    icons = [
        child
        for block in data.get("blocks", [])
        for child in block.get("children", [])
        if child.get("kind") == "icon"
    ]
    assert len(icons) >= _MIN_ICON_COUNT, (
        f"p0082 has {len(icons)} icons, expected >= {_MIN_ICON_COUNT}"
    )


@pytest.mark.skipif(not _RENDER_FILE.exists(), reason="exported render data not present")
def test_p0082_required_symbols_present() -> None:
    """p0082 render page must include all required gameplay symbol IDs."""
    data = json.loads(_RENDER_FILE.read_text())
    found_symbols = {
        child.get("symbol_id")
        for block in data.get("blocks", [])
        for child in block.get("children", [])
        if child.get("kind") == "icon"
    }
    missing = _REQUIRED_SYMBOLS - found_symbols
    assert not missing, f"p0082 is missing symbols: {sorted(missing)}"
