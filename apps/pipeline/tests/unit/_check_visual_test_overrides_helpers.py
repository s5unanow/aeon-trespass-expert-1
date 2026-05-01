"""Shared helpers for `test_check_visual_test_overrides_*.py` (S5U-657).

Leading-underscore filename: pytest does not collect, no conftest collision.
"""

from __future__ import annotations

from pathlib import Path


def write_spec(scan_dir: Path, name: str, body: str) -> Path:
    """Create `scan_dir/name` containing `body`. Returns the spec path."""
    scan_dir.mkdir(parents=True, exist_ok=True)
    spec = scan_dir / name
    spec.write_text(body, encoding="utf-8")
    return spec
