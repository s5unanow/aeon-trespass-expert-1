"""Layered TOML config loader."""

from __future__ import annotations

import tomllib
from pathlib import Path

from atr_pipeline.config.models import DocumentBuildConfig


def _find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start to find the repo root (contains pyproject.toml)."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current


def _load_toml(path: Path) -> dict[str, object]:
    """Load a TOML file and return its contents as a dict."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    """Recursively merge override into base, preferring override values."""
    merged: dict[str, object] = {**base}
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def load_document_config(
    document_id: str,
    *,
    repo_root: Path | None = None,
    env: str | None = None,
) -> DocumentBuildConfig:
    """Load and merge base + env + document config, then validate.

    Config resolution order:
    1. configs/base.toml (defaults)
    2. configs/{env}.toml (if env is set, e.g. "ci")
    3. configs/documents/{document_id}.toml (document-specific)
    """
    root = _find_repo_root(repo_root)
    configs_dir = root / "configs"

    # 1. Base config
    base_path = configs_dir / "base.toml"
    if not base_path.exists():
        msg = f"Base config not found: {base_path}"
        raise FileNotFoundError(msg)
    merged: dict[str, object] = _load_toml(base_path)

    # 2. Environment overlay
    if env:
        env_path = configs_dir / f"{env}.toml"
        if env_path.exists():
            env_data = _load_toml(env_path)
            merged = _deep_merge(merged, env_data)

    # 3. Document config
    doc_path = configs_dir / "documents" / f"{document_id}.toml"
    if not doc_path.exists():
        msg = f"Document config not found: {doc_path}"
        raise FileNotFoundError(msg)
    doc_data = _load_toml(doc_path)
    merged = _deep_merge(merged, doc_data)

    # Resolve paths
    merged["repo_root"] = str(root)
    artifact_root = merged.get("artifact_root", "artifacts")
    if not Path(str(artifact_root)).is_absolute():
        merged["artifact_root"] = str(root / str(artifact_root))

    return DocumentBuildConfig.model_validate(merged)
