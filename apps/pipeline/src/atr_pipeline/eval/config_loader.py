"""Load golden set TOML configuration files."""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath

from atr_pipeline.config.loader import _find_repo_root
from atr_pipeline.eval.models import GoldenSetConfig

# Files in configs/golden_sets/ that are not golden set definitions.
_NON_GOLDEN_FILES = frozenset({"coverage_matrix.toml"})


def load_golden_set(name: str, *, repo_root: Path | None = None) -> GoldenSetConfig:
    """Load a golden set config by name from configs/golden_sets/{name}.toml."""
    safe = PurePosixPath(name)
    if safe.parent != PurePosixPath(".") or str(safe) != name:
        msg = f"Invalid golden set name (must be a simple filename): {name}"
        raise ValueError(msg)
    root = repo_root or _find_repo_root()
    path = root / "configs" / "golden_sets" / f"{name}.toml"
    if not path.exists():
        msg = f"Golden set config not found: {path}"
        raise FileNotFoundError(msg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return GoldenSetConfig.model_validate(data)


def discover_golden_sets(*, repo_root: Path | None = None) -> list[str]:
    """Return sorted names of all golden set configs in configs/golden_sets/."""
    root = repo_root or _find_repo_root()
    gs_dir = root / "configs" / "golden_sets"
    if not gs_dir.is_dir():
        return []
    return sorted(p.stem for p in gs_dir.glob("*.toml") if p.name not in _NON_GOLDEN_FILES)
