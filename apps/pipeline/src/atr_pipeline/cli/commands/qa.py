"""CLI command: atr qa — run QA checks on existing artifacts."""

from __future__ import annotations

from collections import Counter

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.eval.confidence_policy import ConfidenceBandPolicy, load_confidence_bands
from atr_pipeline.stages.qa.auto_fix_runner import (
    AutoFixPageBundle,
    apply_patches_and_rerun,
    resolve_latest_render_ref,
    write_patches,
)
from atr_pipeline.stages.qa.metrics import compute_qa_metrics, format_metrics_digest
from atr_pipeline.stages.qa.publishable import filter_publishable_pages
from atr_pipeline.stages.qa.registry import QAPageContext, QARule, get_all_rules
from atr_pipeline.stages.qa.review_pack import build_review_pack
from atr_pipeline.stages.qa.rules.confidence_band_rule import evaluate_confidence_band
from atr_pipeline.stages.qa.user_feedback import load_user_feedback_records
from atr_pipeline.stages.qa.waivers import apply_waivers, load_waivers
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.patch_set_v1 import PatchSetV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderPageV1


def qa(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    review_pack: bool = typer.Option(
        False,
        "--review-pack",
        help="Generate review pack JSON for blocking and qa_required findings",
    ),
    auto_fix: bool = typer.Option(
        False,
        "--auto-fix",
        help="Generate patch files for deterministic auto-fixes",
    ),
    apply_fixes: bool = typer.Option(
        False,
        "--apply",
        help=(
            "Apply generated patches to render artifacts and re-run QA."
            " Requires --auto-fix. Default is dry-run (writes patch files only)."
        ),
    ),
) -> None:
    """Run QA checks on existing artifacts for a document."""
    if apply_fixes and not auto_fix:
        typer.echo("--apply requires --auto-fix", err=True)
        raise typer.Exit(2)

    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)

    page_ids = _resolve_page_ids(store, doc)
    if not page_ids:
        typer.echo("No EN IR pages found. Run pipeline first.", err=True)
        raise typer.Exit(1)

    rules = get_all_rules()
    confidence_policy = load_confidence_bands(repo_root=config.repo_root)
    # S5U-701 round 2 / S5U-730 — compute the reader-manifest-aligned
    # page set once and reuse for both the initial QA pass and the
    # post-apply re-run. Delegates to the shared
    # ``stages.qa.publishable.filter_publishable_pages`` helper so the
    # CLI and the stage runner cannot drift on what "publishable" means
    # (image-injection-rescued pages must be included so DEAD_PAGE_REF
    # does not false-positive on references to article-mode pages whose
    # render is empty but whose source-PDF imagery the exporter rescues).
    publishable_page_ids = filter_publishable_pages(store, doc, page_ids)
    known_page_numbers = _page_ids_to_numbers(publishable_page_ids)
    all_records, bundles = _collect_records(
        store, doc, page_ids, rules, confidence_policy, auto_fix, known_page_numbers
    )

    waivers_dir = config.repo_root / config.qa.waivers_dir
    waivers = load_waivers(waivers_dir, doc)
    if waivers:
        typer.echo(f"Loaded {len(waivers)} waiver(s) for {doc}")
    all_records = apply_waivers(all_records, waivers)

    _print_summary(all_records)

    block_on = set(config.qa.block_publish_on)

    metrics = compute_qa_metrics(
        document_id=doc,
        run_id="cli",
        edition="",
        page_ids=page_ids,
        records=all_records,
        block_on=block_on,
    )
    typer.echo(format_metrics_digest(metrics))

    if review_pack:
        _write_review_pack(store, doc, all_records, block_on)

    patches_written: list[tuple[AutoFixPageBundle, PatchSetV1]] = []
    if auto_fix:
        patches_written = write_patches(store, doc, all_records, bundles)

    final_records = all_records
    if apply_fixes:
        typer.echo("\nApplying patches and re-running QA…")
        # Reuse the reader-manifest-aligned page set computed above so the
        # re-run path agrees with the initial QA pass on what "dead page
        # ref" means (Codex REVISE round 2).
        result = apply_patches_and_rerun(
            store=store,
            doc=doc,
            waivers_dir=waivers_dir,
            rules=rules,
            patches=patches_written,
            pre_records=all_records,
            known_page_numbers=known_page_numbers,
        )
        # `result.post_records` only covers pages the apply loop
        # successfully refreshed. Keep pre-fix records for every other
        # page so blockers outside the auto-fixer's scope still count
        # toward the final exit code.
        kept = [r for r in all_records if r.page_id not in result.refreshed_page_ids]
        final_records = kept + result.post_records

    has_blocking = any(r.severity.value in block_on and not r.waived for r in final_records)
    if has_blocking:
        raise typer.Exit(1)


def _collect_records(
    store: ArtifactStore,
    doc: str,
    page_ids: list[str],
    rules: list[QARule],
    confidence_policy: ConfidenceBandPolicy,
    auto_fix: bool,
    known_page_numbers: frozenset[int],
) -> tuple[list[QARecordV1], dict[str, AutoFixPageBundle]]:
    """Load artifacts + evaluate rules across pages.

    Returns the raw (pre-waiver) record list and, when *auto_fix* is
    true, a map of page_id → bundle for the downstream patch writer.
    """
    records: list[QARecordV1] = []
    bundles: dict[str, AutoFixPageBundle] = {}

    for page_id in page_ids:
        en_ir = _load_ir(store, doc, "page_ir.v1.en", page_id)
        ru_ir = _load_ir(store, doc, "page_ir.v1.ru", page_id)
        render = _load_render(store, doc, page_id)

        if en_ir is None or ru_ir is None or render is None:
            typer.echo(f"  SKIP {page_id}: missing artifacts", err=True)
            continue

        ctx = QAPageContext(
            source_ir=en_ir,
            target_ir=ru_ir,
            render_page=render,
            known_page_numbers=known_page_numbers,
        )
        for rule in rules:
            records.extend(rule.evaluate(ctx))

        # Confidence-band records: same semantics as QAStage.run so the CLI
        # entrypoint and the stage entrypoint produce identical record sets
        # for the same artifacts.
        records.extend(evaluate_confidence_band(en_ir, confidence_policy))

        # User-feedback records are persisted per edition by the ingest
        # script; the CLI surfaces both editions so triage can see the full
        # picture regardless of which edition is currently being built.
        for edition in ("en", "ru"):
            records.extend(
                load_user_feedback_records(
                    store=store,
                    document_id=doc,
                    edition=edition,
                    page_id=page_id,
                )
            )

        if auto_fix:
            ref = resolve_latest_render_ref(store, doc, page_id)
            if ref is not None:
                bundles[page_id] = AutoFixPageBundle(
                    page_id=page_id,
                    en_ir=en_ir,
                    ru_ir=ru_ir,
                    render=render,
                    render_ref=ref,
                )

    return records, bundles


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


def _page_ids_to_numbers(page_ids: list[str]) -> frozenset[int]:
    """Convert p0008-style ids to the set of PDF page numbers (S5U-701).

    Mirrors ``atr_pipeline.stages.qa.stage._page_ids_to_numbers``; kept
    local to this CLI module to avoid cross-module coupling between the
    stage runner and the ad-hoc CLI entrypoint.
    """
    numbers: set[int] = set()
    for pid in page_ids:
        if len(pid) < 2 or not pid.startswith("p"):
            continue
        try:
            numbers.add(int(pid[1:]))
        except ValueError:
            continue
    return frozenset(numbers)


def _load_ir(
    store: ArtifactStore,
    doc: str,
    family: str,
    page_id: str,
) -> PageIRV1 | None:
    data = store.load_latest_json(
        document_id=doc, schema_family=family, scope="page", entity_id=page_id
    )
    return PageIRV1.model_validate(data) if data else None


def _load_render(
    store: ArtifactStore,
    doc: str,
    page_id: str,
) -> RenderPageV1 | None:
    data = store.load_latest_json(
        document_id=doc, schema_family="render_page.v1", scope="page", entity_id=page_id
    )
    return RenderPageV1.model_validate(data) if data else None


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
