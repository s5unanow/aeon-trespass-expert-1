"""S5U-1006 — AGY/Gemini CLI adapters must close stdin (``stdin=subprocess.DEVNULL``).

Defense-in-depth follow-up to S5U-1004 (which fixed the three Codex adapters).
The independent review of S5U-1004 found the *same* missing-``stdin=`` shape in
the two other CLI translate adapters:

* ``agy_cli_adapter.py`` — ``subprocess.run(...)`` with no ``stdin=`` redirect.
* ``gemini_cli_adapter.py`` — same.

Unlike ``codex exec``, both ``agy --print`` and ``gemini -p`` were empirically
verified to run headless without hanging (S5U-997 handoff, 2026-06-08), so this
is not a confirmed bug — it is closing the class so a future CLI/version change
can't reintroduce a headless stdin hang on the translate stage.

Two layers of regression coverage mirror ``test_codex_stdin_devnull_s5u1004.py``:

1. **Behavioral** (``test_*_completes_when_parent_leaks_open_stdin``): a real
   ``/bin/sh`` fake-CLI stub that reads stdin to EOF *before* writing its output
   to stdout, run with the parent's fd 0 deliberately pointed at an open, empty,
   never-closed pipe. That reproduces the exact headless condition — a child
   inheriting an open stdin with no EOF blocks, and the adapter times out. With
   the fix, the adapter passes ``stdin=DEVNULL`` so the stub sees immediate EOF
   and completes. The deliberate fd-0 swap is required because pytest's default
   ``--capture=fd`` points fd 0 at ``/dev/null`` (immediate EOF), which would
   mask the bug and make the test pass with *or* without the fix (the
   S5U-604/S5U-606 false-green trap).

2. **White-box** (``test_*_passes_stdin_devnull``): patch ``subprocess.run`` and
   assert each adapter passes ``stdin=subprocess.DEVNULL``. Platform-independent
   and deterministically red-before (the kwarg is simply absent pre-fix).

Note: unlike the Codex adapters (output via ``--output-last-message`` file), the
AGY/Gemini adapters return their result on **stdout**, so the stubs ``echo`` the
canned JSON after draining stdin. ``GeminiCLIAdapter`` hardcodes ``gemini`` as
the executable, so the behavioral test installs a ``gemini`` stub on ``PATH``;
``AgyCLIAdapter`` accepts ``executable=`` directly.

Red-before confirmation: ran locally at this branch with the two
``stdin=subprocess.DEVNULL`` lines reverted; both behavioral tests errored with
``RuntimeError: ... timed out after 6s`` and both white-box tests failed their
``assert ... is subprocess.DEVNULL`` (kwarg absent). Re-applying the fix turns
all four green. See the PR body for the captured excerpts.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from atr_pipeline.services.llm.agy_cli_adapter import AgyCLIAdapter
from atr_pipeline.services.llm.gemini_cli_adapter import GeminiCLIAdapter
from tests.unit.services.llm._codex_cli_helpers import make_batch, make_valid_result_json

# ── Behavioral reproduction helpers ──────────────────────────────────


def _stub_source(payload: str) -> str:
    """A ``/bin/sh`` fake-CLI that blocks on an open stdin, then echoes payload.

    ``cat >/dev/null`` reads stdin to EOF *first* — that is the step that hangs
    forever when the parent leaks an open stdin and returns instantly when stdin
    is ``/dev/null``. Only after EOF does it emit the canned JSON on stdout,
    which is how both adapters receive their result.
    """
    # Single-quote the payload for the heredoc-free echo; the JSON contains no
    # single quotes (json.dumps escapes none into the ASCII keys, and Russian
    # values carry none), so a single-quoted shell string is safe.
    assert "'" not in payload, "payload must not contain single quotes for the sh stub"
    return "#!/bin/sh\ncat >/dev/null\ncat <<'__ATR_EOF__'\n" + payload + "\n__ATR_EOF__\nexit 0\n"


def _write_stub(tmp_path: Path, name: str, payload: str) -> Path:
    stub = tmp_path / name
    stub.write_text(_stub_source(payload), encoding="utf-8")
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


# ── Behavioral tests: real stub hangs on open stdin without the fix ──


def test_agy_translate_completes_when_parent_leaks_open_stdin(tmp_path: Path) -> None:
    """AGY adapter must not hang when the parent's stdin is left open."""
    stub = _write_stub(tmp_path, "fake_agy.sh", make_valid_result_json())
    adapter = AgyCLIAdapter(executable=str(stub), timeout_seconds=6)
    with _leaked_open_stdin():
        response = adapter.translate_batch(make_batch())
    assert response.result.batch_id == "b1"


def test_gemini_translate_completes_when_parent_leaks_open_stdin(
    tmp_path: Path,
) -> None:
    """Gemini adapter must not hang when the parent's stdin is left open.

    ``GeminiCLIAdapter`` hardcodes ``gemini`` as the executable, so the stub is
    installed on ``PATH`` under that name.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _write_stub(bindir, "gemini", make_valid_result_json())
    adapter = GeminiCLIAdapter(timeout_seconds=6)
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bindir}{os.pathsep}{old_path}"
    try:
        with _leaked_open_stdin():
            response = adapter.translate_batch(make_batch())
    finally:
        os.environ["PATH"] = old_path
    assert response.result.batch_id == "b1"


# ── White-box tests: each adapter passes stdin=subprocess.DEVNULL ────


def _capture_stdin(
    record: dict[str, Any],
    payload: str,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """``subprocess.run`` side_effect that records kwargs and returns *payload* on stdout."""

    def _side(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        record["kwargs"] = kwargs
        argv = args[0] if args else kwargs.get("args")
        assert isinstance(argv, list)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=payload, stderr="")

    return _side


def test_agy_translate_passes_stdin_devnull() -> None:
    record: dict[str, Any] = {}
    adapter = AgyCLIAdapter()
    with patch(
        "atr_pipeline.services.llm.agy_cli_adapter.subprocess.run",
        side_effect=_capture_stdin(record, make_valid_result_json()),
    ):
        adapter.translate_batch(make_batch())
    assert record["kwargs"].get("stdin") is subprocess.DEVNULL


def test_gemini_translate_passes_stdin_devnull() -> None:
    record: dict[str, Any] = {}
    adapter = GeminiCLIAdapter()
    with patch(
        "atr_pipeline.services.llm.gemini_cli_adapter.subprocess.run",
        side_effect=_capture_stdin(record, make_valid_result_json()),
    ):
        adapter.translate_batch(make_batch())
    assert record["kwargs"].get("stdin") is subprocess.DEVNULL
