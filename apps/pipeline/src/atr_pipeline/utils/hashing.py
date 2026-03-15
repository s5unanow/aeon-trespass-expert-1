"""Content hashing utilities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_str(text: str) -> str:
    """Return the hex SHA-256 of a UTF-8 string."""
    return sha256_bytes(text.encode("utf-8"))


def content_hash(data: object) -> str:
    """Deterministic content hash of a JSON-serializable object.

    Uses sorted keys and no whitespace for stability.
    """
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_str(canonical)[:12]
