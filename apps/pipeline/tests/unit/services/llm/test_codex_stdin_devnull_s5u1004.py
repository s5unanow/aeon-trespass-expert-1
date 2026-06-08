# ruff: noqa: RUF001  — Russian payloads are part of the behavior under test.
"""S5U-1004 — Codex adapters must close stdin (``stdin=subprocess.DEVNULL``).

Bare ``codex exec "<prompt>"`` blocks forever on ``Reading additional input
from stdin...`` when run non-interactively (background shell, CI, headless
``atr run``). The three translation-side Codex adapters shelled out via
``subprocess.run(argv, capture_output=True, ...)`` with **no** ``stdin=``
redirect, so they inherited the parent's stdin and hung headless. The fix is
``stdin=subprocess.DEVNULL`` on each call.

Two layers of regression coverage:

1. **Behavioral** (``test_*_completes_when_parent_leaks_open_stdin``): a real
   fake-``codex`` stub that reads stdin to EOF *before* writing its output, run
   with the parent's fd 0 deliberately pointed at an open, empty, never-closed
   pipe. That reproduces the exact headless condition — a child inheriting an
   open stdin with no EOF blocks, and the adapter times out. With the fix, the
   adapter passes ``stdin=DEVNULL`` so the stub sees immediate EOF and
   completes. The deliberate fd-0 swap is required because pytest's default
   ``--capture=fd`` points fd 0 at ``/dev/null`` (immediate EOF), which would
   mask the bug and make the test pass with *or* without the fix (the
   S5U-604/S5U-606 false-green trap).

2. **White-box** (``test_*_passes_stdin_devnull``): patch ``subprocess.run`` and
   assert each adapter passes ``stdin=subprocess.DEVNULL``. Platform-independent
   and deterministically red-before (the kwarg is simply absent pre-fix).

Red-before confirmation: ran locally at this branch with the three
``stdin=subprocess.DEVNULL`` lines reverted; the behavioral translate test
errored with ``RuntimeError: Codex CLI timed out after 6s`` and each white-box
test failed its ``assert ... is subprocess.DEVNULL`` (kwarg absent). Re-applying
the fix turns all four green. See the PR body for the captured excerpts.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from atr_pipeline.services.llm.codex_cli_adapter import CodexCLIAdapter
from atr_pipeline.services.llm.russian_style_critic import (
    CriticPageRequest,
    CriticParagraph,
)
from atr_pipeline.services.llm.russian_style_critic_codex import (
    CodexRussianStyleCritic,
)
from atr_pipeline.services.llm.russian_style_repair import (
    RepairPageRequest,
    RepairParagraph,
)
from atr_pipeline.services.llm.russian_style_repair_codex import (
    CodexRussianStyleRepair,
)
from tests.unit.services.llm._codex_cli_helpers import (
    argv_value_after,
    make_batch,
    make_valid_result_json,
)

# ── Payloads the fake codex writes into --output-last-message ─────────

_CRITIC_PAYLOAD = json.dumps(
    {
        "document_id": "doc",
        "page_id": "p0001",
        "findings": [
            {
                "paragraph_id": "p0001",
                "severity": "warning",
                "quote": "с великим трепетом",
                "why": "Коллокация звучит канцелярски.",
                "suggestions": ["Заменить на «с благоговейным трепетом»."],
            }
        ],
    },
    ensure_ascii=False,
)

_REPAIR_PAYLOAD = json.dumps(
    {
        "document_id": "doc",
        "page_id": "p0001",
        "repairs": [{"paragraph_id": "p0001", "repaired_text": "Исправленный текст."}],
    },
    ensure_ascii=False,
)


def _critic_request() -> CriticPageRequest:
    return CriticPageRequest(
        document_id="doc",
        page_id="p0001",
        paragraphs=[
            CriticParagraph(
                paragraph_id="p0001",
                block_type="paragraph",
                ru_text="с великим трепетом",
                source_text="with great trepidation",
            )
        ],
    )


def _repair_request() -> RepairPageRequest:
    return RepairPageRequest(
        document_id="doc",
        page_id="p0001",
        paragraphs=[
            RepairParagraph(
                paragraph_id="p0001",
                block_type="paragraph",
                current_text="с великим трепетом",
                source_text="with great trepidation",
            )
        ],
    )


# ── Behavioral reproduction helpers ──────────────────────────────────


def _stub_source(payload_path: Path) -> str:
    """A ``/bin/sh`` fake-``codex`` that blocks on an open stdin.

    ``cat >/dev/null`` reads stdin to EOF *first* — that is the step that hangs
    forever when the parent leaks an open stdin and returns instantly when
    stdin is ``/dev/null``. Only after EOF does it copy the canned payload into
    the path named by ``--output-last-message``.
    """
    return (
        "#!/bin/sh\n"
        "cat >/dev/null\n"
        'out=""\n'
        'prev=""\n'
        'for arg in "$@"; do\n'
        '  if [ "$prev" = "--output-last-message" ]; then\n'
        '    out="$arg"\n'
        "  fi\n"
        '  prev="$arg"\n'
        "done\n"
        'if [ -z "$out" ]; then\n'
        '  echo "stub: missing --output-last-message" >&2\n'
        "  exit 3\n"
        "fi\n"
        f'cp "{payload_path}" "$out"\n'
        "exit 0\n"
    )


def _write_codex_stub(tmp_path: Path, payload: str) -> Path:
    payload_path = tmp_path / "codex_payload.json"
    payload_path.write_text(payload, encoding="utf-8")
    stub = tmp_path / "fake_codex.sh"
    stub.write_text(_stub_source(payload_path), encoding="utf-8")
    stub.chmod(0o755)
    return stub


@contextmanager
def _leaked_open_stdin() -> Iterator[None]:
    """Point the process's fd 0 at an open, empty, never-closed pipe.

    A child inheriting this fd sees an open stdin with no data and no EOF, so a
    blocking read hangs — the real headless condition. Restored in ``finally``.
    """
    read_fd, write_fd = os.pipe()
    saved_stdin = os.dup(0)
    try:
        os.dup2(read_fd, 0)
        yield
    finally:
        os.dup2(saved_stdin, 0)
        os.close(saved_stdin)
        os.close(read_fd)
        os.close(write_fd)


# ── Behavioral test: real stub hangs on open stdin without the fix ───


def test_codex_translate_completes_when_parent_leaks_open_stdin(
    tmp_path: Path,
) -> None:
    """Translate adapter must not hang when the parent's stdin is left open."""
    stub = _write_codex_stub(tmp_path, make_valid_result_json())
    adapter = CodexCLIAdapter(
        model="gpt-5.5",
        executable=str(stub),
        timeout_seconds=6,
        json_events=False,
    )
    with _leaked_open_stdin():
        response = adapter.translate_batch(make_batch())
    assert response.result.batch_id == "b1"


# ── White-box tests: each adapter passes stdin=subprocess.DEVNULL ────


def _capture_stdin(
    record: dict[str, Any],
    payload: str,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """``subprocess.run`` side_effect that records kwargs and writes *payload*."""

    def _side(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        record["kwargs"] = kwargs
        argv = args[0] if args else kwargs.get("args")
        assert isinstance(argv, list)
        last_msg_path = argv_value_after(argv, "--output-last-message")
        assert last_msg_path is not None
        Path(last_msg_path).write_text(payload, encoding="utf-8")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    return _side


def test_codex_translate_passes_stdin_devnull() -> None:
    record: dict[str, Any] = {}
    adapter = CodexCLIAdapter(model="gpt-5.5", json_events=False)
    with patch(
        "atr_pipeline.services.llm.codex_cli_adapter.subprocess.run",
        side_effect=_capture_stdin(record, make_valid_result_json()),
    ):
        adapter.translate_batch(make_batch())
    assert record["kwargs"].get("stdin") is subprocess.DEVNULL


def test_codex_critic_passes_stdin_devnull() -> None:
    record: dict[str, Any] = {}
    critic = CodexRussianStyleCritic(model="gpt-5.5", json_events=False)
    with patch(
        "atr_pipeline.services.llm.russian_style_critic_codex.subprocess.run",
        side_effect=_capture_stdin(record, _CRITIC_PAYLOAD),
    ):
        critic.critique_page(_critic_request())
    assert record["kwargs"].get("stdin") is subprocess.DEVNULL


def test_codex_repair_passes_stdin_devnull() -> None:
    record: dict[str, Any] = {}
    repair = CodexRussianStyleRepair(model="gpt-5.5", json_events=False)
    with patch(
        "atr_pipeline.services.llm.russian_style_repair_codex.subprocess.run",
        side_effect=_capture_stdin(record, _REPAIR_PAYLOAD),
    ):
        repair.repair_page(_repair_request())
    assert record["kwargs"].get("stdin") is subprocess.DEVNULL
