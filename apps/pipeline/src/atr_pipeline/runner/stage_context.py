"""StageContext — per-invocation runtime dependencies for a stage."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from atr_pipeline.config.models import DocumentBuildConfig
from atr_pipeline.store.artifact_store import ArtifactStore


@dataclass
class StageContext:
    """Runtime context passed to every stage invocation."""

    run_id: str
    document_id: str
    config: DocumentBuildConfig
    artifact_store: ArtifactStore
    registry_conn: sqlite3.Connection
    repo_root: Path = field(default_factory=lambda: Path("."))
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("atr_pipeline"))
