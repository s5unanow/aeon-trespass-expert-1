"""Auto-fix CLI runner — orchestrate patch write and apply loop.

Split from :mod:`atr_pipeline.cli.commands.qa` to keep the command file
under the 400-line limit while owning the full dry-run / apply / re-run
pipeline used by ``atr qa --auto-fix [--apply]``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import typer

from atr_pipeline.stages.patch.applicator import PatchError, apply_patches
from atr_pipeline.stages.qa.auto_fix import generate_patches_for_page
from atr_pipeline.stages.qa.registry import QAPageContext, QARule
from atr_pipeline.stages.qa.waivers import apply_waivers, load_waivers
from atr_pipeline.store.artifact_ref import ArtifactRef
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.patch_set_v1 import PatchSetV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderPageV1


@dataclass(frozen=True)
class AutoFixPageBundle:
    """Per-page data required to build and apply auto-fix patches."""

    page_id: str
    en_ir: PageIRV1
    ru_ir: PageIRV1
    render: RenderPageV1
    render_ref: ArtifactRef


def resolve_latest_render_ref(
    store: ArtifactStore,
    doc: str,
    page_id: str,
) -> ArtifactRef | None:
    """Return an ``ArtifactRef`` for the most-recent render_page of *page_id*."""
    entity_dir = store.root / doc / "render_page.v1" / "page" / page_id
    if not entity_dir.exists():
        return None
    jsons = list(entity_dir.glob("*.json"))
    if not jsons:
        return None
    latest = max(jsons, key=lambda p: p.stat().st_mtime)
    content_hash = latest.stem  # filename is "{content_hash}.json"
    return ArtifactRef(
        document_id=doc,
        schema_family="render_page.v1",
        scope="page",
        entity_id=page_id,
        content_hash=content_hash,
    )


def write_patches(
    store: ArtifactStore,
    doc: str,
    records: list[QARecordV1],
    bundles: dict[str, AutoFixPageBundle],
) -> list[tuple[AutoFixPageBundle, PatchSetV1]]:
    """Write patch files for auto-fixable findings.

    Returns ``(bundle, patch)`` pairs for pages where at least one
    operation was emitted. Waived records are filtered out inside
    :func:`generate_patches_for_page`.
    """
    fixable = [r for r in records if r.auto_fix and r.auto_fix.available and not r.waived]
    if not fixable:
        typer.echo("\nNo auto-fixable findings.")
        return []

    by_page: dict[str, list[QARecordV1]] = {}
    for r in fixable:
        pid = r.page_id or ""
        by_page.setdefault(pid, []).append(r)

    written: list[tuple[AutoFixPageBundle, PatchSetV1]] = []
    for page_id, page_records in sorted(by_page.items()):
        bundle = bundles.get(page_id)
        if bundle is None:
            continue
        patch_set = generate_patches_for_page(
            page_records,
            bundle.render,
            target_ref=bundle.render_ref,
        )
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
        written.append((bundle, patch_set))

    typer.echo(f"\nAuto-fix: {len(written)} patch file(s) generated from {len(fixable)} finding(s)")
    return written


@dataclass(frozen=True)
class ApplyRerunResult:
    """Outcome of applying patches + re-running QA.

    ``post_records`` lists the post-waiver QA records from re-evaluating
    the pages in ``refreshed_page_ids``. Pages whose patch application
    failed are absent from both sets — callers must fall back to the
    pre-fix records for those pages.
    """

    post_records: list[QARecordV1]
    refreshed_page_ids: frozenset[str]


def apply_patches_and_rerun(
    *,
    store: ArtifactStore,
    doc: str,
    waivers_dir: Path,
    rules: list[QARule],
    patches: list[tuple[AutoFixPageBundle, PatchSetV1]],
    pre_records: list[QARecordV1],
) -> ApplyRerunResult:
    """Apply generated patches, re-run QA, and print a before/after diff.

    The original ``pre_records`` must be the post-waiver QA output from
    the initial pass; it's used as the "before" baseline for the diff.

    Returns an :class:`ApplyRerunResult` pairing the post-fix records
    with the set of page IDs that were actually refreshed, so callers
    can merge those into the pre-fix record set for unmutated pages.
    """
    if not patches:
        typer.echo("No patches to apply.")
        return ApplyRerunResult(post_records=[], refreshed_page_ids=frozenset())

    refreshed: dict[str, AutoFixPageBundle] = {}
    for bundle, patch_set in patches:
        try:
            patched_dict = apply_patches(bundle.render.model_dump(mode="json"), patch_set)
        except PatchError as exc:
            typer.echo(f"  Apply failed for {bundle.page_id}: {exc}", err=True)
            continue
        patched = RenderPageV1.model_validate(patched_dict)
        new_ref = store.put_json(
            document_id=doc,
            schema_family="render_page.v1",
            scope="page",
            entity_id=bundle.page_id,
            data=patched,
        )
        typer.echo(f"  Applied → {new_ref.relative_path}")
        refreshed[bundle.page_id] = AutoFixPageBundle(
            page_id=bundle.page_id,
            en_ir=bundle.en_ir,
            ru_ir=bundle.ru_ir,
            render=patched,
            render_ref=new_ref,
        )

    # Re-run QA across just the mutated pages, then re-apply waivers.
    post_records: list[QARecordV1] = []
    for page_id in sorted(refreshed):
        post_bundle = refreshed[page_id]
        ctx = QAPageContext(
            source_ir=post_bundle.en_ir,
            target_ir=post_bundle.ru_ir,
            render_page=post_bundle.render,
        )
        for rule in rules:
            post_records.extend(rule.evaluate(ctx))

    waivers = load_waivers(waivers_dir, doc)
    post_records = apply_waivers(post_records, waivers)

    pre_counts = _count_by_code(r for r in pre_records if r.page_id in refreshed and not r.waived)
    post_counts = _count_by_code(r for r in post_records if not r.waived)

    _print_diff(pre_counts, post_counts)
    return ApplyRerunResult(
        post_records=post_records,
        refreshed_page_ids=frozenset(refreshed),
    )


def _count_by_code(records: Iterable[QARecordV1]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for r in records:
        counts[r.code] += 1
    return counts


def _print_diff(pre: Counter[str], post: Counter[str]) -> None:
    """Print a before/after diff table over QA codes."""
    codes = sorted(set(pre) | set(post))
    if not codes:
        typer.echo("\nNo findings on apply-target pages.")
        return
    typer.echo(f"\n{'CODE':<30} {'BEFORE':>8} {'AFTER':>8} {'DELTA':>8}")
    typer.echo("-" * 56)
    total_before = 0
    total_after = 0
    for code in codes:
        b = pre.get(code, 0)
        a = post.get(code, 0)
        total_before += b
        total_after += a
        typer.echo(f"{code:<30} {b:>8} {a:>8} {a - b:>+8}")
    typer.echo("-" * 56)
    typer.echo(f"{'TOTAL':<30} {total_before:>8} {total_after:>8} {total_after - total_before:>+8}")
