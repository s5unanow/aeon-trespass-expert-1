"""Shared fixtures for ``CodexCLIAdapter`` unit tests (S5U-747).

These helpers build minimal valid translation batches/results and a
``subprocess.run`` side-effect factory that writes the desired payload
into the file passed via ``--output-last-message``. The split exists so
``test_codex_cli_adapter.py`` and ``test_codex_cli_argv.py`` stay under
the 400-line file ceiling.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment

if TYPE_CHECKING:
    from collections.abc import Callable


def make_batch(batch_id: str = "b1") -> TranslationBatchV1:
    """Return a minimal :class:`TranslationBatchV1` with one segment."""
    return TranslationBatchV1(
        batch_id=batch_id,
        segments=[
            TranslationSegment(
                segment_id="s1",
                block_type="paragraph",
                source_inline=[{"type": "text", "text": "Hello"}],  # type: ignore[list-item]
            ),
        ],
    )


def make_valid_result_json(batch_id: str = "b1") -> str:
    """Return a minimal valid TranslationResultV1 JSON for *batch_id*."""
    return json.dumps(
        {
            "batch_id": batch_id,
            "segments": [
                {
                    "segment_id": "s1",
                    "target_inline": [{"type": "text", "text": "Привет"}],
                    "concept_realizations": [],
                },
            ],
        },
        ensure_ascii=False,
    )


def argv_value_after(argv: list[str], flag: str) -> str | None:
    """Return the value following *flag* in *argv*, or None if absent."""
    try:
        i = argv.index(flag)
    except ValueError:
        return None
    if i + 1 >= len(argv):
        return None
    return argv[i + 1]


def last_msg_writer(
    payload: str | bytes,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Build a ``subprocess.run`` side_effect that writes *payload* into the
    file named by ``--output-last-message`` in the call's argv and returns
    a successful :class:`subprocess.CompletedProcess`."""

    def _side_effect(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        argv = args[0] if args else kwargs.get("args")
        assert isinstance(argv, list), "subprocess.run must be called with an argv list"
        last_msg_path = argv_value_after(argv, "--output-last-message")
        assert last_msg_path is not None
        if isinstance(payload, bytes):
            Path(last_msg_path).write_bytes(payload)
        else:
            Path(last_msg_path).write_text(payload, encoding="utf-8")
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout="",
            stderr="",
        )

    return _side_effect
