"""Realpath containment checks for externally declared source paths."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def resolve_allowed_path(
    raw_path: str,
    *,
    base_dir: Path,
    allowed_roots: Sequence[Path],
    label: str,
) -> Path:
    """Resolve a declared path and require it to remain under an allowed root."""
    if "\x00" in raw_path:
        msg = f"{label} contains a null byte"
        raise ValueError(msg)

    declared = Path(raw_path)
    if ".." in declared.parts:
        msg = f"{label} contains a traversal component ('..')"
        raise ValueError(msg)

    candidate = declared if declared.is_absolute() else base_dir / declared
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        msg = f"{label} not found: {candidate}"
        raise FileNotFoundError(msg) from exc

    roots = tuple(root.resolve(strict=True) for root in allowed_roots)
    if not roots:
        msg = f"{label} cannot be resolved without an allowed root"
        raise ValueError(msg)
    if not any(resolved.is_relative_to(root) for root in roots):
        msg = f"{label} resolves outside allowed roots: {resolved}"
        raise ValueError(msg)
    if not resolved.is_file():
        msg = f"{label} is not a file: {resolved}"
        raise ValueError(msg)
    return resolved
