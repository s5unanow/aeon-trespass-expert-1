"""JSON Schema helpers for Codex CLI structured output."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def codex_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a Codex-compatible schema with every object property required."""
    strict = deepcopy(schema)
    _require_all_properties(strict)
    return strict


def _require_all_properties(node: Any) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties)
        for value in node.values():
            _require_all_properties(value)
    elif isinstance(node, list):
        for item in node:
            _require_all_properties(item)
