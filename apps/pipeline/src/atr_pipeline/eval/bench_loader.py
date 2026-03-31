"""Load benchmark ladder TOML configurations."""

from __future__ import annotations

import tomllib
from pathlib import Path, PurePosixPath

from atr_pipeline.config.loader import _find_repo_root
from atr_pipeline.eval.bench_models import BenchmarkLadderConfig


def load_benchmark_ladder(
    name: str,
    *,
    repo_root: Path | None = None,
) -> BenchmarkLadderConfig:
    """Load a benchmark ladder config from configs/benchmarks/{name}.toml."""
    safe = PurePosixPath(name)
    if safe.parent != PurePosixPath(".") or str(safe) != name:
        msg = f"Invalid benchmark ladder name: {name}"
        raise ValueError(msg)
    root = repo_root or _find_repo_root()
    path = root / "configs" / "benchmarks" / f"{name}.toml"
    if not path.exists():
        msg = f"Benchmark ladder config not found: {path}"
        raise FileNotFoundError(msg)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    config = BenchmarkLadderConfig.model_validate(data)
    config.checkpoints.sort(key=lambda c: c.order)
    return config


def discover_benchmark_ladders(*, repo_root: Path | None = None) -> list[str]:
    """Return sorted names of all benchmark ladder configs."""
    root = repo_root or _find_repo_root()
    bench_dir = root / "configs" / "benchmarks"
    if not bench_dir.is_dir():
        return []
    return sorted(p.stem for p in bench_dir.glob("*.toml"))
