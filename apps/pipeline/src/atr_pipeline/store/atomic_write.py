"""Atomic file write — ensures partial writes never become visible."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write data atomically by writing to a temp file, then renaming."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, data)
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
