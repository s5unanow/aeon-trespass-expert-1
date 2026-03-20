"""Load golden set TOML configuration files."""

from __future__ import annotations

import tomllib
from pathlib import Path

from atr_pipeline.eval.models import GoldenSetConfig


def load_golden_set(name: str, *, repo_root: Path | None = None) -> GoldenSetConfig:
    """Load a golden set config by name from configs/golden_sets/{name}.toml."""
    root = repo_root or _find_repo_root()
    path = root / "configs" / "golden_sets" / f"{name}.toml"
    if not path.exists():
        msg = f"Golden set config not found: {path}"
        raise FileNotFoundError(msg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return GoldenSetConfig.model_validate(data)


def _find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start to find the repo root (contains pyproject.toml)."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current
