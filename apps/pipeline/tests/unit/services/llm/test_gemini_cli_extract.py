"""Tests for Gemini CLI response extraction logic."""

from __future__ import annotations

import json

import pytest

from atr_pipeline.services.llm.gemini_cli_adapter import _extract_result


def _valid_result() -> dict[str, object]:
    return {
        "batch_id": "tr.p0001.01",
        "segments": [
            {
                "segment_id": "blk_001",
                "target_inline": [{"type": "text", "text": "Тест"}],
                "concept_realizations": [],
            },
        ],
    }


def test_extract_direct_json() -> None:
    raw = json.dumps(_valid_result())
    assert _extract_result(raw)["batch_id"] == "tr.p0001.01"


def test_extract_markdown_fenced() -> None:
    raw = f"```json\n{json.dumps(_valid_result())}\n```"
    assert _extract_result(raw)["batch_id"] == "tr.p0001.01"


def test_extract_bare_fence() -> None:
    raw = f"```\n{json.dumps(_valid_result())}\n```"
    assert _extract_result(raw)["batch_id"] == "tr.p0001.01"


def test_extract_from_envelope_response_key() -> None:
    raw = json.dumps({"response": json.dumps(_valid_result())})
    assert _extract_result(raw)["batch_id"] == "tr.p0001.01"


def test_extract_from_envelope_text_key() -> None:
    raw = json.dumps({"text": json.dumps(_valid_result())})
    assert _extract_result(raw)["batch_id"] == "tr.p0001.01"


def test_extract_rejects_json_array() -> None:
    with pytest.raises(RuntimeError, match="not a JSON object"):
        _extract_result("[1, 2, 3]")


def test_extract_rejects_unrecognized_dict() -> None:
    raw = json.dumps({"status": "ok", "data": "irrelevant"})
    with pytest.raises(RuntimeError, match="does not contain a valid translation"):
        _extract_result(raw)


def test_extract_rejects_garbage() -> None:
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _extract_result("not json at all")


def test_extract_finds_json_in_mixed_output() -> None:
    raw = f"Here is the result:\n{json.dumps(_valid_result())}\nDone."
    assert _extract_result(raw)["batch_id"] == "tr.p0001.01"
