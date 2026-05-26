"""Shared parsing helpers for JSON-emitting CLI LLM adapters."""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def extract_translation_result(raw: str, *, provider_label: str) -> dict[str, object]:
    """Parse CLI output into a translation result dict.

    Handles direct JSON, markdown-fenced JSON, and simple response envelopes.
    """
    text = raw.strip()

    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                msg = f"{provider_label} output is not valid JSON: {text[:200]}"
                raise RuntimeError(msg) from None
        else:
            msg = f"{provider_label} output is not valid JSON: {text[:200]}"
            raise RuntimeError(msg) from None

    if not isinstance(data, dict):
        msg = f"{provider_label} output is not a JSON object: {type(data).__name__}"
        raise RuntimeError(msg)

    if "batch_id" in data and "segments" in data:
        return data

    for key in ("response", "text", "output"):
        val = data.get(key)
        if isinstance(val, str):
            try:
                inner = json.loads(val)
            except json.JSONDecodeError:
                continue
            if isinstance(inner, dict) and "batch_id" in inner:
                return inner

    msg = f"{provider_label} output does not contain a valid translation result"
    raise RuntimeError(msg)
