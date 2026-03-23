"""Per-run log file persistence — duplicates log output to a run-specific file."""

from __future__ import annotations

import logging
from pathlib import Path


def attach_run_log_handler(artifact_root: Path, run_id: str) -> logging.FileHandler:
    """Add a file handler for the run log and return it for later removal."""
    log_dir = artifact_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_id}.log"

    handler = logging.FileHandler(str(log_path), encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    return handler


def detach_run_log_handler(handler: logging.FileHandler) -> None:
    """Remove the file handler and close the underlying file."""
    logging.getLogger().removeHandler(handler)
    handler.close()
