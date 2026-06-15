"""Atomic file write — ensures partial writes never become visible."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write data atomically by writing to a temp file, then renaming.

    ``write(2)`` may write fewer bytes than requested (signal interruption;
    >INT_MAX buffers on some platforms for huge rasters), so the payload is
    written in a loop until every byte is on disk — a short write must never be
    renamed into place as a truncated-but-"committed" artifact. The temp file is
    then ``fsync``'d before the rename so a crash after ``os.replace`` cannot
    expose a zero-length file (durable rename, undurable data).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            written += os.write(fd, view[written:])
        os.fsync(fd)
        os.close(fd)
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically using UTF-8 encoding."""
    atomic_write_bytes(path, text.encode("utf-8"))
