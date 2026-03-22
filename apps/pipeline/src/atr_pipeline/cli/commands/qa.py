"""CLI command: atr qa — run QA checks on existing artifacts."""

from __future__ import annotations

import json
from collections import Counter

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.stages.qa.auto_fix import generate_patches_for_page
from atr_pipeline.stages.qa.registry import QAPageContext, get_all_rules
from atr_pipeline.stages.qa.review_pack import build_review_pack
from atr_pipeline.stages.qa.waivers import apply_waivers, load_waivers
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderPageV1


def qa(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    review_pack: bool = typer.Option(
        False,
        "--review-pack",
        help="Generate review pack JSON for blocking findings",
    ),
    auto_fix: bool = typer.Option(
        False,
        "--auto-fix",
        help="Generate patch files for deterministic auto-fixes",
    ),
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
    page_renders: dict[str, RenderPageV1] = {}

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
        if auto_fix:
            page_renders[page_id] = render

    waivers_dir = config.repo_root / config.qa.waivers_dir
    waivers = load_waivers(waivers_dir, doc)
    if waivers:
        typer.echo(f"Loaded {len(waivers)} waiver(s) for {doc}")
    all_records = apply_waivers(all_records, waivers)

    _print_summary(all_records)

    block_on = set(config.qa.block_publish_on)

    if review_pack:
        _write_review_pack(store, doc, all_records, block_on)

    if auto_fix:
        _write_auto_fix_patches(store, doc, all_records, page_renders)

    has_blocking = any(r.severity.value in block_on and not r.waived for r in all_records)
    if has_blocking:
        raise typer.Exit(1)


def _write_auto_fix_patches(
    store: ArtifactStore,
    doc: str,
    records: list[QARecordV1],
    page_renders: dict[str, RenderPageV1],
) -> None:
    """Generate and persist auto-fix patch sets grouped by page."""
    fixable = [r for r in records if r.auto_fix and r.auto_fix.available and not r.waived]
    if not fixable:
        typer.echo("\nNo auto-fixable findings.")
        return

    by_page: dict[str, list[QARecordV1]] = {}
    for r in fixable:
        pid = r.page_id or ""
        by_page.setdefault(pid, []).append(r)

    written = 0
    for page_id, page_records in sorted(by_page.items()):
        render = page_renders.get(page_id)
        if render is None:
            continue
        patch_set = generate_patches_for_page(page_records, render)
        if patch_set is None:
            continue
        ref = store.put_json(
            document_id=doc,
            schema_family="patch_set.v1",
            scope="page",
            entity_id=page_id,
            data=patch_set,
        )
        typer.echo(f"  Patch: {ref.relative_path}")
        written += 1

    typer.echo(f"\nAuto-fix: {written} patch file(s) generated from {len(fixable)} finding(s)")


def _write_review_pack(
    store: ArtifactStore,
    doc: str,
    records: list[QARecordV1],
    block_on: set[str],
) -> None:
    """Generate and persist a review pack."""
    pack = build_review_pack(
        document_id=doc,
        run_id="cli",
        records=records,
        block_on=block_on,
    )
    ref = store.put_json(
        document_id=doc,
        schema_family="review_pack.v1",
        scope="document",
        entity_id=doc,
        data=pack,
    )
    typer.echo(f"\nReview pack written: {ref.relative_path}")


def _resolve_page_ids(store: ArtifactStore, doc: str) -> list[str]:
    ir_dir = store.root / doc / "page_ir.v1.en" / "page"
    if ir_dir.exists():
        return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())
    return []


def _load_ir(
    store: ArtifactStore,
    doc: str,
    family: str,
    page_id: str,
) -> PageIRV1 | None:
    page_dir = store.root / doc / family / "page" / page_id
    if not page_dir.exists():
        return None
    jsons = sorted(page_dir.glob("*.json"))
    if not jsons:
        return None
    return PageIRV1.model_validate(json.loads(jsons[-1].read_text()))


def _load_render(
    store: ArtifactStore,
    doc: str,
    page_id: str,
) -> RenderPageV1 | None:
    page_dir = store.root / doc / "render_page.v1" / "page" / page_id
    if not page_dir.exists():
        return None
    jsons = sorted(page_dir.glob("*.json"))
    if not jsons:
        return None
    return RenderPageV1.model_validate(json.loads(jsons[-1].read_text()))


def _print_summary(records: list[QARecordV1]) -> None:
    active = [r for r in records if not r.waived]
    waived = [r for r in records if r.waived]

    if not active and not waived:
        typer.echo("QA passed: all checks clean.")
        return

    if active:
        code_counts: Counter[str] = Counter()
        severity_map: dict[str, str] = {}
        for r in active:
            code_counts[r.code] += 1
            severity_map[r.code] = r.severity.value

        typer.echo(f"\n{'CODE':<30} {'SEVERITY':<12} {'COUNT':>5}")
        typer.echo("-" * 49)
        for code, count in code_counts.most_common():
            typer.echo(f"{code:<30} {severity_map[code]:<12} {count:>5}")
        typer.echo("-" * 49)
        total = sum(code_counts.values())
        typer.echo(f"{'TOTAL':<30} {'':12} {total:>5}")

    if waived:
        typer.echo(f"\nWaived: {len(waived)} finding(s)")
        waived_codes: Counter[str] = Counter()
        for r in waived:
            waived_codes[r.code] += 1
        for code, count in waived_codes.most_common():
            typer.echo(f"  {code}: {count}")
