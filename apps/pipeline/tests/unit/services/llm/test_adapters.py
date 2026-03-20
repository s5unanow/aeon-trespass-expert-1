"""Tests for LLM adapter error paths and response handling.

All tests mock the SDK clients — no real network calls are made.
"""

from __future__ import annotations

import json
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from atr_schemas.page_ir_v1 import TextInline
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)


def _sample_batch() -> TranslationBatchV1:
    return TranslationBatchV1(
        batch_id="tr.p0001.01",
        source_lang="en",
        target_lang="ru",
        segments=[
            TranslationSegment(
                segment_id="blk_001",
                block_type="heading",
                source_inline=[TextInline(text="Attack Test")],
                context=SegmentContext(page_id="p0001"),
            ),
        ],
    )


def _valid_result_json(batch_id: str = "tr.p0001.01") -> str:
    return json.dumps(
        {
            "batch_id": batch_id,
            "segments": [
                {
                    "segment_id": "blk_001",
                    "target_inline": [{"type": "text", "text": "Тест атаки"}],
                    "concept_realizations": [],
                },
            ],
        }
    )


def _mock_openai_module() -> tuple[ModuleType, MagicMock]:
    """Return (module, MockOpenAIClass) so the adapter can be constructed."""
    mod = ModuleType("openai")
    mock_cls = MagicMock()
    mod.OpenAI = mock_cls  # type: ignore[attr-defined]
    return mod, mock_cls


def _mock_anthropic_module() -> tuple[ModuleType, MagicMock]:
    mod = ModuleType("anthropic")
    mock_cls = MagicMock()
    mod.Anthropic = mock_cls  # type: ignore[attr-defined]
    return mod, mock_cls


def _mock_google_modules() -> tuple[dict[str, ModuleType], MagicMock]:
    google_mod = ModuleType("google")
    genai_mod = ModuleType("google.genai")
    mock_client_cls = MagicMock()
    genai_mod.Client = mock_client_cls  # type: ignore[attr-defined]
    # Also need types sub-module for translate_batch
    types_mod = ModuleType("google.genai.types")
    types_mod.Content = MagicMock()  # type: ignore[attr-defined]
    types_mod.Part = MagicMock()  # type: ignore[attr-defined]
    types_mod.GenerateContentConfig = MagicMock()  # type: ignore[attr-defined]
    genai_mod.types = types_mod  # type: ignore[attr-defined]
    google_mod.genai = genai_mod  # type: ignore[attr-defined]
    modules = {
        "google": google_mod,
        "google.genai": genai_mod,
        "google.genai.types": types_mod,
    }
    return modules, mock_client_cls


# --- Import error paths ---


def test_openai_import_error() -> None:
    """OpenAIAdapter should raise ImportError when openai is missing."""
    with patch.dict("sys.modules", {"openai": None}):
        from importlib import reload

        import atr_pipeline.services.llm.openai_adapter as mod

        reload(mod)
        with pytest.raises(ImportError, match="openai package is required"):
            mod.OpenAIAdapter()


def test_anthropic_import_error() -> None:
    """AnthropicAdapter should raise ImportError when anthropic is missing."""
    with patch.dict("sys.modules", {"anthropic": None}):
        from importlib import reload

        import atr_pipeline.services.llm.anthropic_adapter as mod

        reload(mod)
        with pytest.raises(ImportError, match="anthropic package is required"):
            mod.AnthropicAdapter()


def test_gemini_import_error() -> None:
    """GeminiAdapter should raise ImportError when google-genai is missing."""
    with patch.dict("sys.modules", {"google": None, "google.genai": None}):
        from importlib import reload

        import atr_pipeline.services.llm.gemini_adapter as mod

        reload(mod)
        with pytest.raises(ImportError, match="google-genai package is required"):
            mod.GeminiAdapter()


# --- OpenAI response handling ---


def test_openai_empty_response_raises() -> None:
    """OpenAI returning None content should raise RuntimeError."""
    mod, mock_cls = _mock_openai_module()
    mock_client = MagicMock()
    mock_cls.return_value = mock_client

    with patch.dict("sys.modules", {"openai": mod}):
        from atr_pipeline.services.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(model="gpt-4o")
        choice = SimpleNamespace(message=SimpleNamespace(content=None))
        mock_client.chat.completions.create.return_value = SimpleNamespace(choices=[choice])

        with pytest.raises(RuntimeError, match="OpenAI returned empty response"):
            adapter.translate_batch(_sample_batch())


def test_openai_valid_response_returns_result() -> None:
    """OpenAI returning valid JSON should produce a TranslationResultV1."""
    mod, mock_cls = _mock_openai_module()
    mock_client = MagicMock()
    mock_cls.return_value = mock_client

    with patch.dict("sys.modules", {"openai": mod}):
        from atr_pipeline.services.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(model="gpt-4o")
        choice = SimpleNamespace(message=SimpleNamespace(content=_valid_result_json()))
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[choice],
            usage=None,
        )

        resp = adapter.translate_batch(_sample_batch())
        assert resp.result.batch_id == "tr.p0001.01"
        assert len(resp.result.segments) == 1
        assert resp.meta.provider == "openai"


def test_openai_model_profile_override() -> None:
    """model_profile should override the default model."""
    mod, mock_cls = _mock_openai_module()
    mock_client = MagicMock()
    mock_cls.return_value = mock_client

    with patch.dict("sys.modules", {"openai": mod}):
        from atr_pipeline.services.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(model="gpt-4o")
        choice = SimpleNamespace(message=SimpleNamespace(content=_valid_result_json()))
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[choice],
            usage=None,
        )

        adapter.translate_batch(_sample_batch(), model_profile="gpt-4o-mini")
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o-mini"


# --- Anthropic response handling ---


def test_anthropic_missing_tool_use_raises() -> None:
    """Anthropic response without tool_use block should raise RuntimeError."""
    mod, mock_cls = _mock_anthropic_module()
    mock_client = MagicMock()
    mock_cls.return_value = mock_client

    with patch.dict("sys.modules", {"anthropic": mod}):
        from atr_pipeline.services.llm.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(model="claude-sonnet-4-6")
        text_block = SimpleNamespace(type="text", text="I will translate this.")
        mock_client.messages.create.return_value = SimpleNamespace(content=[text_block])

        with pytest.raises(RuntimeError, match="did not contain expected tool use"):
            adapter.translate_batch(_sample_batch())


def test_anthropic_valid_tool_use_returns_result() -> None:
    """Anthropic response with valid tool_use block should return result."""
    mod, mock_cls = _mock_anthropic_module()
    mock_client = MagicMock()
    mock_cls.return_value = mock_client

    with patch.dict("sys.modules", {"anthropic": mod}):
        from atr_pipeline.services.llm.anthropic_adapter import AnthropicAdapter

        adapter = AnthropicAdapter(model="claude-sonnet-4-6")
        tool_block = SimpleNamespace(
            type="tool_use",
            name="submit_translation",
            input=json.loads(_valid_result_json()),
        )
        usage = SimpleNamespace(input_tokens=100, output_tokens=50)
        mock_client.messages.create.return_value = SimpleNamespace(
            content=[tool_block],
            usage=usage,
        )

        resp = adapter.translate_batch(_sample_batch())
        assert resp.result.batch_id == "tr.p0001.01"
        assert len(resp.result.segments) == 1
        assert resp.meta.provider == "anthropic"
        assert resp.meta.input_tokens == 100


# --- Gemini response handling ---


def test_gemini_empty_response_raises() -> None:
    """Gemini returning None text should raise RuntimeError."""
    modules, mock_client_cls = _mock_google_modules()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    with patch.dict("sys.modules", modules):
        from atr_pipeline.services.llm.gemini_adapter import GeminiAdapter

        adapter = GeminiAdapter(model="gemini-2.5-flash")
        mock_client.models.generate_content.return_value = SimpleNamespace(text=None)

        with pytest.raises(RuntimeError, match="Gemini returned empty response"):
            adapter.translate_batch(_sample_batch())


def test_gemini_valid_response_returns_result() -> None:
    """Gemini returning valid JSON should produce a TranslationResultV1."""
    modules, mock_client_cls = _mock_google_modules()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    with patch.dict("sys.modules", modules):
        from atr_pipeline.services.llm.gemini_adapter import GeminiAdapter

        adapter = GeminiAdapter(model="gemini-2.5-flash")
        mock_client.models.generate_content.return_value = SimpleNamespace(
            text=_valid_result_json(),
            usage_metadata=None,
        )

        resp = adapter.translate_batch(_sample_batch())
        assert resp.result.batch_id == "tr.p0001.01"
        assert len(resp.result.segments) == 1
        assert resp.meta.provider == "gemini"


# --- Gemini schema stripping ---


def test_strip_additional_properties() -> None:
    """_strip_additional_properties should remove the key recursively."""
    from atr_pipeline.services.llm.gemini_adapter import _strip_additional_properties

    schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "additionalProperties": False},
            "items_list": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False},
            },
        },
    }
    result = _strip_additional_properties(schema)

    assert "additionalProperties" not in result
    props = result["properties"]
    assert isinstance(props, dict)
    assert "additionalProperties" not in props["name"]
    items_list = props["items_list"]
    assert isinstance(items_list, dict)
    assert "additionalProperties" not in items_list["items"]
