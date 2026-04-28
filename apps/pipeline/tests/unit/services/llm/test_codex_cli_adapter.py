"""Unit tests for :class:`CodexCLIAdapter` — failure modes, parsing, metadata.

Argv-shape tests live in ``test_codex_cli_argv.py`` to keep both files
under the 400-line ceiling.

Red-before anchor (S5U-615 § three-input test discipline): the adapter
file ``apps/pipeline/src/atr_pipeline/services/llm/codex_cli_adapter.py``
did not exist on commit ``afacd3d`` (the S5U-746 merge SHA, the parent
of this branch's first commit). Importing it from any test below produces
``ModuleNotFoundError`` until the adapter module lands. Resolve via
``git cat-file -e afacd3d^{commit}``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atr_pipeline.services.llm.codex_cli_adapter import CodexCLIAdapter
from tests.unit.services.llm._codex_cli_helpers import (
    argv_value_after,
    last_msg_writer,
    make_batch,
    make_valid_result_json,
)

# ── Constructor / allowlist tests ────────────────────────────────────


def test_codex_cli_rejects_invalid_sandbox() -> None:
    """Sandbox values outside the upstream ``[possible values: ...]`` list reject."""
    with pytest.raises(ValueError, match="sandbox"):
        CodexCLIAdapter(model="gpt-5.5", sandbox="full-trust")


def test_codex_cli_rejects_non_never_approval_policy() -> None:
    """Only ``never`` is safe for non-interactive pipeline runs."""
    with pytest.raises(ValueError, match="approval_policy"):
        CodexCLIAdapter(model="gpt-5.5", approval_policy="on-request")


def test_codex_cli_rejects_empty_model() -> None:
    """A non-empty model is required (Codex has no documented default)."""
    with pytest.raises(ValueError, match="model"):
        CodexCLIAdapter(model="")


# ── Subprocess failure mode tests ────────────────────────────────────


def test_codex_cli_missing_executable_raises() -> None:
    """``FileNotFoundError`` from subprocess maps to a clear runtime error."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            side_effect=FileNotFoundError("codex"),
        ),
        pytest.raises(RuntimeError, match="codex CLI not found"),
    ):
        adapter.translate_batch(make_batch())


def test_codex_cli_timeout_raises() -> None:
    """``TimeoutExpired`` maps to a runtime error naming the timeout value."""
    adapter = CodexCLIAdapter(model="gpt-5.5", timeout_seconds=42)
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["codex"], timeout=42),
        ),
        pytest.raises(RuntimeError, match="timed out after 42s"),
    ):
        adapter.translate_batch(make_batch())


def test_codex_cli_nonzero_exit_raises_with_bounded_stderr() -> None:
    """Non-zero return code surfaces the exit code and a bounded stderr snippet."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    long_stderr = "x" * 5000  # well past the 500-char budget
    fake_proc = MagicMock(spec=subprocess.CompletedProcess)
    fake_proc.returncode = 7
    fake_proc.stdout = ""
    fake_proc.stderr = long_stderr
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            return_value=fake_proc,
        ),
        pytest.raises(RuntimeError, match=r"exited with code 7") as excinfo,
    ):
        adapter.translate_batch(make_batch())
    assert len(str(excinfo.value)) < 1000


# ── Output-file parse failure tests ──────────────────────────────────


def test_codex_cli_empty_last_message_raises() -> None:
    """An empty ``--output-last-message`` file is rejected."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            side_effect=last_msg_writer(""),
        ),
        pytest.raises(RuntimeError, match="no final message"),
    ):
        adapter.translate_batch(make_batch())


def test_codex_cli_non_json_output_raises() -> None:
    """A final message that isn't JSON after one fence-strip is rejected."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            side_effect=last_msg_writer("this is not json at all"),
        ),
        pytest.raises(RuntimeError, match="not valid JSON"),
    ):
        adapter.translate_batch(make_batch())


def test_codex_cli_schema_invalid_output_raises() -> None:
    """JSON that doesn't match TranslationResultV1 raises a ValidationError."""
    from pydantic import ValidationError

    adapter = CodexCLIAdapter(model="gpt-5.5")
    bad_json = json.dumps({"not_batch_id": "b1", "segments": "wrong"})
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            side_effect=last_msg_writer(bad_json),
        ),
        pytest.raises(ValidationError),
    ):
        adapter.translate_batch(make_batch())


def test_codex_cli_batch_id_mismatch_raises() -> None:
    """A schema-valid response with the wrong batch_id is rejected."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    wrong_batch = make_valid_result_json("WRONG_BATCH")
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            side_effect=last_msg_writer(wrong_batch),
        ),
        pytest.raises(RuntimeError, match="batch_id"),
    ):
        adapter.translate_batch(make_batch("b1"))


def test_codex_cli_strips_markdown_fence() -> None:
    """Reasoning-model output wrapped in ```json ... ``` is parsed correctly."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    fenced = "```json\n" + make_valid_result_json() + "\n```"
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(fenced),
    ):
        response = adapter.translate_batch(make_batch())
    assert response.result.batch_id == "b1"


# ── Happy-path / metadata tests ──────────────────────────────────────


def test_codex_cli_happy_path_returns_validated_response() -> None:
    """A successful run returns a validated TranslationResponse with rich meta."""
    adapter = CodexCLIAdapter(
        model="gpt-5.5",
        reasoning_effort="xhigh",
        sandbox="read-only",
        approval_policy="never",
    )
    valid = make_valid_result_json()
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(valid),
    ):
        response = adapter.translate_batch(make_batch())
    assert response.result.batch_id == "b1"
    assert response.result.segments[0].segment_id == "s1"
    assert response.meta.provider == "codex-cli"
    assert response.meta.model == "gpt-5.5"
    assert response.meta.raw_response == valid
    assert response.meta.extra["reasoning_effort"] == "xhigh"
    assert response.meta.extra["sandbox"] == "read-only"
    assert response.meta.extra["approval_policy"] == "never"


def test_codex_cli_parses_token_usage_from_event_stream() -> None:
    """When ``--json`` events expose token usage, the adapter records it."""
    adapter = CodexCLIAdapter(model="gpt-5.5", json_events=True)
    valid = make_valid_result_json()
    events = (
        '{"type":"info"}\n'
        '{"usage":{"input_tokens":1234,"output_tokens":567}}\n'
        "not json garbage\n"
        '{"type":"done"}\n'
    )

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        last_msg_path = argv_value_after(argv, "--output-last-message")
        assert last_msg_path is not None
        Path(last_msg_path).write_text(valid, encoding="utf-8")
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout=events,
            stderr="",
        )

    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=_side,
    ):
        response = adapter.translate_batch(make_batch())
    assert response.meta.input_tokens == 1234
    assert response.meta.output_tokens == 567
    assert response.meta.extra["event_count"] == 3


# ── Cleanup / leak tests ─────────────────────────────────────────────


def test_codex_cli_cleans_up_temp_dir_on_success() -> None:
    """The per-call temp dir is removed after a successful run."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    captured: dict[str, str] = {}

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        last_msg_path = argv_value_after(argv, "--output-last-message")
        assert last_msg_path is not None
        captured["dir"] = str(Path(last_msg_path).parent)
        Path(last_msg_path).write_text(make_valid_result_json(), encoding="utf-8")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=_side,
    ):
        adapter.translate_batch(make_batch())
    assert not Path(captured["dir"]).exists()


def test_codex_cli_cleans_up_temp_dir_on_failure() -> None:
    """The per-call temp dir is removed even when the subprocess fails."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    captured: dict[str, str] = {}

    def _side(*args: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        last_msg_path = argv_value_after(argv, "--output-last-message")
        assert last_msg_path is not None
        captured["dir"] = str(Path(last_msg_path).parent)
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="", stderr="boom")

    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            side_effect=_side,
        ),
        pytest.raises(RuntimeError),
    ):
        adapter.translate_batch(make_batch())
    assert not Path(captured["dir"]).exists()


def test_codex_cli_error_message_is_bounded() -> None:
    """Stderr included in error messages is trimmed to ≤500 chars."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    huge = "S" * 100_000
    fake_proc = MagicMock(spec=subprocess.CompletedProcess)
    fake_proc.returncode = 99
    fake_proc.stdout = ""
    fake_proc.stderr = huge
    with (
        patch(
            "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
            return_value=fake_proc,
        ),
        pytest.raises(RuntimeError) as excinfo,
    ):
        adapter.translate_batch(make_batch())
    assert len(str(excinfo.value)) < 1500
