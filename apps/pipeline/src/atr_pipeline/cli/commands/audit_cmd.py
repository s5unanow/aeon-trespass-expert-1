"""CLI command: atr audit — run full-document extraction audit."""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.eval.audit_report import print_audit_summary, write_audit_json
from atr_pipeline.eval.audit_runner import run_audit
from atr_pipeline.store.artifact_store import ArtifactStore


def audit_command(
    doc: str,
    pages: str = "",
    output_json: str = "",
    baseline: str = "",
) -> None:
    """Run a full-document extraction audit (non-blocking diagnostic)."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)

    page_filter = _parse_pages(pages) if pages else None
    baseline_path = Path(baseline) if baseline else None

    report = run_audit(
        document_id=doc,
        store=store,
        page_filter=page_filter,
        baseline_path=baseline_path,
    )

    print_audit_summary(report)

    if output_json:
        write_audit_json(report, Path(output_json))


def _parse_pages(pages_str: str) -> list[str]:
    """Parse comma-separated page IDs."""
    return [p.strip() for p in pages_str.split(",") if p.strip()]
