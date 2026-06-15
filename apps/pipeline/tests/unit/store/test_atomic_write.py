"""Atomic-write resilience (S5U-1223).

``atomic_write_bytes`` writes a temp file then ``os.replace``s it into place so a
partial write never becomes visible. Two hardening gaps the S5U-1223 fix closes:

* the single unchecked ``os.write(fd, data)`` ignored ``write(2)``'s short-write
  contract — ``write`` may return fewer bytes than requested (signal
  interruption; >INT_MAX buffers on macOS for huge rasters). A short write would
  rename a truncated-but-"committed" artifact into place, defeating the module's
  stated invariant. The fix loops until every byte is written.
* the temp file was never fsynced, so a crash after ``os.replace`` could expose a
  zero-length file (rename durable, data not). The fix fsyncs before rename.

These tests drive the loop (via a monkeypatched short-writing ``os.write``) and
pin the existing no-``.tmp``-litter-on-exception cleanup.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from atr_pipeline.store.atomic_write import atomic_write_bytes, atomic_write_text


def test_short_write_loop_writes_full_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short-writing ``os.write`` (≤4 bytes/call) must still persist all bytes.

    Pre-fix the single ``os.write(fd, data)`` wrote only the first chunk and the
    truncated temp file was renamed into place. The loop drives ``os.write`` until
    the whole payload is on disk.
    """
    payload = bytes(range(256)) * 40  # 10_240 bytes — many short-write chunks
    target = tmp_path / "out.bin"
    real_write = os.write

    def _short_write(fd: int, data: bytes) -> int:
        return real_write(fd, data[:4])  # write at most 4 bytes per call

    monkeypatch.setattr(os, "write", _short_write)
    atomic_write_bytes(target, payload)

    assert target.read_bytes() == payload
    # No leftover temp file from the loop.
    assert not list(tmp_path.glob("*.tmp"))


def test_zero_length_payload_writes_empty_file(tmp_path: Path) -> None:
    """An empty payload must produce an empty file, not hang or error.

    Pins the loop's termination on a zero-length write (the loop must not call
    ``os.write`` with an empty slice forever).
    """
    target = tmp_path / "empty.bin"
    atomic_write_bytes(target, b"")
    assert target.read_bytes() == b""
    assert not list(tmp_path.glob("*.tmp"))


def test_exception_leaves_no_tmp_litter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A mid-write failure unlinks the temp file — no ``.tmp`` litter remains.

    Pins the existing ``except BaseException`` cleanup against the loop rewrite:
    an ``OSError`` raised by ``os.write`` must leave the target absent and the
    temp file removed.
    """
    target = tmp_path / "fails.bin"

    def _boom(fd: int, data: bytes) -> int:
        raise OSError("simulated write failure")

    monkeypatch.setattr(os, "write", _boom)
    with pytest.raises(OSError, match="simulated write failure"):
        atomic_write_bytes(target, b"some data")

    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_write_text_roundtrips_utf8(tmp_path: Path) -> None:
    """``atomic_write_text`` encodes UTF-8 and persists via the byte path."""
    target = tmp_path / "text.json"
    atomic_write_text(target, '{"к": "значение"}')
    assert target.read_text(encoding="utf-8") == '{"к": "значение"}'
