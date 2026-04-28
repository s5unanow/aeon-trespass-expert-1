"""Argv-shape tests for :class:`CodexCLIAdapter` (S5U-747).

These tests pin the canonical command-line surface — long flags, no
`shell=True`, no dangerous bypass, per-call temp paths — separately from
the parsing/error-mode tests so each file stays under the 400-line
ceiling.

Red-before anchor: see ``test_codex_cli_adapter.py`` module docstring.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from atr_pipeline.services.llm.codex_cli_adapter import CodexCLIAdapter
from tests.unit.services.llm._codex_cli_helpers import (
    argv_value_after,
    last_msg_writer,
    make_batch,
    make_valid_result_json,
)


def test_codex_cli_argv_uses_canonical_exec_form() -> None:
    """Argv must use ``codex exec`` (not the alias ``codex e``)."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    assert argv[0] == "codex"
    assert argv[1] == "exec"
    assert "e" not in argv[:2]


def test_codex_cli_argv_uses_canonical_long_flags() -> None:
    """``--model`` / ``--sandbox`` not the short ``-m`` / ``-s`` forms."""
    adapter = CodexCLIAdapter(model="gpt-5.5", sandbox="read-only")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    assert "--model" in argv
    assert "--sandbox" in argv
    assert "-m" not in argv
    assert "-s" not in argv
    assert argv_value_after(argv, "--model") == "gpt-5.5"
    assert argv_value_after(argv, "--sandbox") == "read-only"


def test_codex_cli_argv_never_uses_dangerous_bypass() -> None:
    """``--dangerously-bypass-approvals-and-sandbox`` MUST never appear."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    assert "--full-auto" not in argv


def test_codex_cli_argv_sets_approval_policy_via_config() -> None:
    """Approval policy comes through ``-c approval_policy='never'`` (no `--ask-for-approval`)."""
    adapter = CodexCLIAdapter(model="gpt-5.5", approval_policy="never")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    config_overrides = [argv[i + 1] for i, t in enumerate(argv) if t == "-c"]
    matching = [o for o in config_overrides if "approval_policy=" in o]
    assert matching, f"no approval_policy config override in {argv}"
    assert any("'never'" in o or '"never"' in o for o in matching)
    # Interactive forms must be absent.
    assert "--ask-for-approval" not in argv
    assert "-a" not in argv


def test_codex_cli_argv_sets_reasoning_effort_via_config() -> None:
    """Reasoning effort comes through ``-c model_reasoning_effort=...``."""
    adapter = CodexCLIAdapter(model="gpt-5.5", reasoning_effort="xhigh")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    config_overrides = [argv[i + 1] for i, t in enumerate(argv) if t == "-c"]
    assert any("model_reasoning_effort=" in o and "xhigh" in o for o in config_overrides)


def test_codex_cli_argv_uses_per_call_temp_paths() -> None:
    """``--output-schema`` and ``--output-last-message`` paths sit inside a
    process-managed temp dir (NOT the repo root, NOT a fixed path)."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    captured: dict[str, str] = {}

    def _capture(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        schema_path = argv_value_after(argv, "--output-schema")
        last_msg_path = argv_value_after(argv, "--output-last-message")
        assert schema_path is not None
        assert last_msg_path is not None
        captured["schema"] = schema_path
        captured["last_msg"] = last_msg_path
        assert Path(schema_path).is_file()
        Path(last_msg_path).write_text(make_valid_result_json(), encoding="utf-8")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=_capture,
    ):
        adapter.translate_batch(make_batch())
    assert Path(captured["schema"]).parent == Path(captured["last_msg"]).parent
    assert "codex-translate-" in str(Path(captured["last_msg"]).parent.name)
    # Cleanup runs on success — temp directory should be gone.
    assert not Path(captured["last_msg"]).parent.exists()


def test_codex_cli_invokes_subprocess_as_argv_list_not_shell() -> None:
    """``shell=True`` must never be used (argv is always a list)."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    assert isinstance(mock_run.call_args.args[0], list)
    assert mock_run.call_args.kwargs.get("shell", False) is False


def test_codex_cli_argv_includes_skip_git_repo_check() -> None:
    """The adapter may run outside a git checkout — pass ``--skip-git-repo-check``."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    assert "--skip-git-repo-check" in argv


def test_codex_cli_argv_uses_color_never_for_clean_jsonl() -> None:
    """``--color never`` keeps the JSONL event stream free of ANSI codes."""
    adapter = CodexCLIAdapter(model="gpt-5.5")
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    assert argv_value_after(argv, "--color") == "never"


def test_codex_cli_argv_omits_json_when_disabled() -> None:
    """``json_events=False`` removes ``--json`` from argv (no event-stream parsing)."""
    adapter = CodexCLIAdapter(model="gpt-5.5", json_events=False)
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]
    assert "--json" not in argv


def test_codex_cli_argv_keeps_required_flags_for_unattended_use() -> None:
    """Single regression-pin for the S5U-748 success criterion: dropping any
    of ``--output-schema``, ``approval_policy=never``, or ``sandbox=read-only``
    from argv must fail this test.

    Each individual flag is also covered by a dedicated test elsewhere in
    this file; this one explicitly bundles all three so a future refactor
    that "cleans up argv construction" cannot quietly drop one without a
    failing test screaming at the diff.
    """
    adapter = CodexCLIAdapter(
        model="gpt-5.5",
        sandbox="read-only",
        approval_policy="never",
    )
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=last_msg_writer(make_valid_result_json()),
    ) as mock_run:
        adapter.translate_batch(make_batch())
    argv = mock_run.call_args.args[0]

    # 1) --output-schema present and points at a JSON-schema file.
    schema_path = argv_value_after(argv, "--output-schema")
    assert schema_path is not None, "argv must include --output-schema"

    # 2) sandbox=read-only via long flag (the value is asserted on
    # argv directly, not just in the adapter's stored config).
    assert argv_value_after(argv, "--sandbox") == "read-only"

    # 3) approval_policy=never via -c config override (codex exec does
    # not accept --ask-for-approval; -c is the only safe surface).
    config_overrides = [argv[i + 1] for i, t in enumerate(argv) if t == "-c"]
    matching = [o for o in config_overrides if "approval_policy=" in o]
    assert matching, f"-c approval_policy=... must appear in {argv}"
    assert any("'never'" in o or '"never"' in o for o in matching), (
        f"approval_policy must be 'never' for unattended runs; got {matching}"
    )
