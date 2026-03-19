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
    edition: str = "all"
    page_filter: frozenset[str] | None = None

    def filter_pages(self, page_ids: list[str]) -> list[str]:
        """Apply page_filter if set, preserving order."""
        if self.page_filter is None:
            return page_ids
        return [p for p in page_ids if p in self.page_filter]


def parse_page_filter(spec: str) -> frozenset[str]:
    """Parse a page spec like ``"15,18-20"`` into page IDs like ``{"p0015","p0018",...}``."""
    ids: set[str] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            for n in range(lo, hi + 1):
                ids.add(f"p{n:04d}")
        else:
            ids.add(f"p{int(part):04d}")
    return frozenset(ids)
