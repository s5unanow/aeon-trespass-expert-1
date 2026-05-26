# ruff: noqa: RUF001  — Cyrillic expected strings are intentional.
"""Tests for the AGY CLI translation adapter."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

from atr_pipeline.services.llm.agy_cli_adapter import AgyCLIAdapter
from atr_schemas.page_ir_v1 import TextInline
from atr_schemas.translation_batch_v1 import SegmentContext, TranslationBatchV1, TranslationSegment


def _batch() -> TranslationBatchV1:
    return TranslationBatchV1(
        batch_id="tr.p0001.01",
        source_lang="en",
        target_lang="ru",
        segments=[
            TranslationSegment(
                segment_id="blk_001",
                block_type="paragraph",
                source_inline=[TextInline(text="But only a few.")],
                context=SegmentContext(page_id="p0001"),
            )
        ],
    )


def _payload(batch_id: str = "tr.p0001.01") -> str:
    return json.dumps(
        {
            "batch_id": batch_id,
            "segments": [
                {
                    "segment_id": "blk_001",
                    "target_inline": [
                        {"type": "text", "text": "Но зажглись лишь немногие из них."}
                    ],
                    "concept_realizations": [],
                }
            ],
        },
        ensure_ascii=False,
    )


def test_agy_cli_argv_uses_print_mode_and_timeout() -> None:
    adapter = AgyCLIAdapter(
        model="gemini-3-pro",
        reasoning_effort="high",
        executable="/tmp/agy",
        timeout_seconds=900,
    )
    argv = adapter._build_argv("prompt")  # type: ignore[attr-defined]

    assert argv == ["/tmp/agy", "--print-timeout", "900s", "--print", "prompt"]


def test_agy_cli_prompt_records_requested_profile() -> None:
    adapter = AgyCLIAdapter(model="gemini-3-pro", reasoning_effort="high")
    prompt = adapter._build_prompt(_batch())  # type: ignore[attr-defined]

    assert "gemini-3-pro with high effort" in prompt
    assert "But only a few" in prompt
    assert "Но зажглись лишь немногие из них" in prompt


def test_agy_cli_translate_batch_parses_json() -> None:
    adapter = AgyCLIAdapter(model="gemini-3-pro", executable="/tmp/agy")

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        assert argv[0] == "/tmp/agy"
        assert "--print" in argv
        return subprocess.CompletedProcess(argv, 0, stdout=_payload(), stderr="")

    with patch("atr_pipeline.services.llm.agy_cli_adapter.subprocess.run", side_effect=_side):
        response = adapter.translate_batch(_batch())

    assert response.meta.provider == "agy-cli"
    assert response.meta.model == "agy-session-config"
    assert response.meta.extra["requested_model"] == "gemini-3-pro"
    assert response.meta.extra["requested_reasoning_effort"] == "high"
    assert response.meta.extra["effective_model_verified"] is False
    assert response.result.segments[0].target_inline[0].text == (
        "Но зажглись лишь немногие из них."
    )


def test_agy_cli_batch_id_mismatch_raises() -> None:
    adapter = AgyCLIAdapter(model="gemini-3-pro", executable="/tmp/agy")

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        return subprocess.CompletedProcess(argv, 0, stdout=_payload("wrong"), stderr="")

    with patch("atr_pipeline.services.llm.agy_cli_adapter.subprocess.run", side_effect=_side):
        import pytest

        with pytest.raises(RuntimeError, match="batch_id"):
            adapter.translate_batch(_batch())


def test_agy_cli_stdout_error_raises() -> None:
    adapter = AgyCLIAdapter(model="gemini-3-pro", executable="/tmp/agy")

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="Error: timed out waiting for response",
            stderr="",
        )

    with patch("atr_pipeline.services.llm.agy_cli_adapter.subprocess.run", side_effect=_side):
        import pytest

        with pytest.raises(RuntimeError, match="reported an error"):
            adapter.translate_batch(_batch())


def test_agy_cli_parse_error_mentions_agy() -> None:
    adapter = AgyCLIAdapter(model="gemini-3-pro", executable="/tmp/agy")

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        return subprocess.CompletedProcess(argv, 0, stdout="not json", stderr="")

    with patch("atr_pipeline.services.llm.agy_cli_adapter.subprocess.run", side_effect=_side):
        import pytest

        with pytest.raises(RuntimeError, match="AGY CLI output is not valid JSON"):
            adapter.translate_batch(_batch())
