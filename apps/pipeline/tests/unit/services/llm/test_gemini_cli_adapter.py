"""Tests for the GeminiCLIAdapter (S5U-677 split from test_adapters.py).

All tests mock subprocess — no real CLI invocations are made. The
adapter under test is `atr_pipeline.services.llm.gemini_cli_adapter`,
which shells out to the `gemini` CLI binary; its sibling SDK adapter
(`gemini_adapter`) lives in test_adapters.py because it shares the
``sys.modules``-patching idiom with the OpenAI/Anthropic SDK adapters.
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.unit.services.llm._translation_fixtures import sample_batch, valid_result_json


def test_gemini_cli_not_found_raises() -> None:
    """GeminiCLIAdapter should raise RuntimeError when gemini is not on PATH."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(model="gemini-2.5-flash")
    with (
        patch("subprocess.run", side_effect=FileNotFoundError("gemini")),
        pytest.raises(RuntimeError, match="gemini CLI not found"),
    ):
        adapter.translate_batch(sample_batch())


def test_gemini_cli_nonzero_exit_raises() -> None:
    """Non-zero exit code should raise RuntimeError with stderr."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(model="gemini-2.5-flash")
    proc = SimpleNamespace(returncode=1, stdout="", stderr="quota exceeded")
    with (
        patch("subprocess.run", return_value=proc),
        pytest.raises(RuntimeError, match=r"exited with code 1.*quota exceeded"),
    ):
        adapter.translate_batch(sample_batch())


def test_gemini_cli_empty_output_raises() -> None:
    """Empty stdout should raise RuntimeError."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(model="gemini-2.5-flash")
    proc = SimpleNamespace(returncode=0, stdout="", stderr="")
    with (
        patch("subprocess.run", return_value=proc),
        pytest.raises(RuntimeError, match="empty output"),
    ):
        adapter.translate_batch(sample_batch())


def test_gemini_cli_valid_response_returns_result() -> None:
    """Valid JSON output should produce a TranslationResultV1."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(model="gemini-2.5-flash")
    proc = SimpleNamespace(returncode=0, stdout=valid_result_json(), stderr="")
    with patch("subprocess.run", return_value=proc):
        resp = adapter.translate_batch(sample_batch())
        assert resp.result.batch_id == "tr.p0001.01"
        assert len(resp.result.segments) == 1
        assert resp.meta.provider == "gemini-cli"


def test_gemini_cli_model_profile_override() -> None:
    """model_profile should override the default model in the CLI args."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(model="gemini-2.5-flash")
    proc = SimpleNamespace(returncode=0, stdout=valid_result_json(), stderr="")
    with patch("subprocess.run", return_value=proc) as mock_run:
        adapter.translate_batch(sample_batch(), model_profile="gemini-2.5-pro")
        args = mock_run.call_args[0][0]
        assert "--model" in args
        model_idx = args.index("--model")
        assert args[model_idx + 1] == "gemini-2.5-pro"


def test_gemini_cli_timeout_raises() -> None:
    """Subprocess timeout should raise RuntimeError."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(model="gemini-2.5-flash", timeout_seconds=10)
    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gemini", 10)),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        adapter.translate_batch(sample_batch())


def test_gemini_cli_extracts_from_markdown_fence() -> None:
    """JSON wrapped in markdown code fences should be extracted."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    fenced = f"```json\n{valid_result_json()}\n```"
    adapter = GeminiCLIAdapter(model="gemini-2.5-flash")
    proc = SimpleNamespace(returncode=0, stdout=fenced, stderr="")
    with patch("subprocess.run", return_value=proc):
        resp = adapter.translate_batch(sample_batch())
        assert resp.result.batch_id == "tr.p0001.01"


def test_gemini_cli_extracts_from_envelope() -> None:
    """Response wrapped in an envelope should be extracted."""
    from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter

    envelope = json.dumps({"response": valid_result_json()})
    adapter = GeminiCLIAdapter(model="gemini-2.5-flash")
    proc = SimpleNamespace(returncode=0, stdout=envelope, stderr="")
    with patch("subprocess.run", return_value=proc):
        resp = adapter.translate_batch(sample_batch())
        assert resp.result.batch_id == "tr.p0001.01"
