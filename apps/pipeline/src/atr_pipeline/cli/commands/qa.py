"""CLI command: atr qa — run QA checks on existing artifacts."""

from __future__ import annotations

import json
from collections import Counter

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.stages.qa.registry import QAPageContext, get_all_rules
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import Severity
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderPageV1


def qa(
    doc: str = typer.Option(..., "--doc", help="Document id"),
) -> None:
    """Run QA checks on existing artifacts for a document."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)

    page_ids = _resolve_page_ids(store, doc)
    if not page_ids:
        typer.echo("No EN IR pages found. Run pipeline first.", err=True)
        raise typer.Exit(1)

    rules = get_all_rules()
    all_records: list[QARecordV1] = []

    for page_id in page_ids:
        en_ir = _load_ir(store, doc, "page_ir.v1.en", page_id)
        ru_ir = _load_ir(store, doc, "page_ir.v1.ru", page_id)
        render = _load_render(store, doc, page_id)

        if en_ir is None or ru_ir is None or render is None:
            typer.echo(f"  SKIP {page_id}: missing artifacts", err=True)
            continue

        ctx = QAPageContext(source_ir=en_ir, target_ir=ru_ir, render_page=render)
        for rule in rules:
            all_records.extend(rule.evaluate(ctx))

    _print_summary(all_records)

    has_blocking = any(r.severity in (Severity.ERROR, Severity.CRITICAL) for r in all_records)
    if has_blocking:
        raise typer.Exit(1)


def _resolve_page_ids(store: ArtifactStore, doc: str) -> list[str]:
    ir_dir = store.root / doc / "page_ir.v1.en" / "page"
    if ir_dir.exists():
        return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())
    return []


def _load_ir(store: ArtifactStore, doc: str, family: str, page_id: str) -> PageIRV1 | None:
    page_dir = store.root / doc / family / "page" / page_id
    if not page_dir.exists():
        return None
    jsons = sorted(page_dir.glob("*.json"))
    if not jsons:
        return None
    return PageIRV1.model_validate(json.loads(jsons[-1].read_text()))


def _load_render(store: ArtifactStore, doc: str, page_id: str) -> RenderPageV1 | None:
    page_dir = store.root / doc / "render_page.v1" / "page" / page_id
    if not page_dir.exists():
        return None
    jsons = sorted(page_dir.glob("*.json"))
    if not jsons:
        return None
    return RenderPageV1.model_validate(json.loads(jsons[-1].read_text()))


def _print_summary(records: list[QARecordV1]) -> None:
    if not records:
        typer.echo("QA passed: all checks clean.")
        return

    code_counts: Counter[str] = Counter()
    severity_map: dict[str, str] = {}
    for r in records:
        code_counts[r.code] += 1
        severity_map[r.code] = r.severity.value

    typer.echo(f"\n{'CODE':<30} {'SEVERITY':<12} {'COUNT':>5}")
    typer.echo("-" * 49)
    for code, count in code_counts.most_common():
        typer.echo(f"{code:<30} {severity_map[code]:<12} {count:>5}")
    typer.echo("-" * 49)

    total = sum(code_counts.values())
    typer.echo(f"{'TOTAL':<30} {'':12} {total:>5}")
