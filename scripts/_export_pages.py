"""Render-page + glossary write helpers for the web export.

Extracted from ``export_to_web.py`` (S5U-890) so the entry script stays under
the repo's 400-line ceiling once the two-phase fail-closed commit landed. These
are pure transform-and-write helpers: every artifact has already been resolved
and ref-bound to a single run upstream (``_export_run.resolve_run``); nothing
here enumerates the artifact store or chooses between competing artifacts.

``edition_dir`` overrides the default ``doc_public / edition`` target so the
two-phase commit can build into a staging dir before the atomic swap. The
staging dir must stay a direct child of ``doc_public`` so
``_export_validation.validate_asset_existence`` (which derives
``doc_public = data_dir.parent.parent``) still resolves figure src paths against
the live shared ``images/`` dir.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from _export_blocks import (  # noqa: E402
    inject_image_figures,
    namespace_bare_figures,
    postprocess_blocks,
    rewrite_facsimile_urls,
    rewrite_figure_urls,
    text_content,
)
from _export_toc import extract_toc_sections  # noqa: E402

from atr_pipeline.store.atomic_write import atomic_write_text  # noqa: E402

_KIND_MAP = {
    "list_item": "list_items",
    "figure": "figures",
    "heading": "headings",
    "paragraph": "paragraphs",
}


def _count_block_stats(blocks: list[dict], stats: dict) -> None:
    """Accumulate block kind counts into stats dict."""
    for b in blocks:
        key = _KIND_MAP.get(b.get("kind", ""))
        if key:
            stats[key] += 1
        if b.get("kind") == "paragraph" and len(text_content(b)) > 800:
            stats["long_paras"] += 1


def export_pages(
    doc_id: str,
    edition: str,
    render_pages: dict[str, dict],
    doc_public: Path,
    page_images: dict[str, list[dict]],
    provenance: dict[str, str] | None = None,
    *,
    edition_dir: Path | None = None,
) -> None:
    """Export ref-bound render pages with navigation and image figures.

    ``render_pages`` maps page_id → already-resolved render-page payload,
    selected from a single pipeline run (S5U-869) rather than picked by mtime.
    All artifact selection happens upstream in ``_export_run.resolve_run`` so
    this function only transforms + writes; it never enumerates the artifact
    store or chooses between competing artifacts.

    ``edition_dir`` overrides the default ``doc_public / edition`` target so the
    two-phase commit (S5U-890) can build into a staging dir; it must stay a
    direct child of ``doc_public`` so ``validate_asset_existence`` still resolves
    figure src paths against the live shared ``images/`` dir.
    """
    edition_dir = doc_public / edition if edition_dir is None else edition_dir
    data_dir = edition_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale render_page files from prior exports
    for stale in data_dir.glob("render_page.*.json"):
        stale.unlink()

    exported: list[tuple[str, dict]] = []  # (page_id, data) for exported pages
    pages_meta = []
    stats = {"list_items": 0, "figures": 0, "headings": 0, "paragraphs": 0, "long_paras": 0}

    for pid in sorted(render_pages):
        best = render_pages[pid]

        # Rewrite legacy bare imgNNNN asset IDs to namespaced pid.imgNNNN
        namespace_bare_figures(best, pid)

        # Rewrite pipeline-relative figure src paths for all page types
        rewrite_figure_urls(best, doc_id)

        if best.get("presentation_mode") == "facsimile":
            rewrite_facsimile_urls(best, doc_id)
        else:
            best["blocks"] = postprocess_blocks(best.get("blocks", []))
            inject_image_figures(best, pid, page_images.get(pid, []))

        # Skip pages with no renderable content (e.g. blank cover pages)
        is_facsimile = best.get("presentation_mode") == "facsimile"
        if not is_facsimile and not best.get("blocks"):
            continue

        _count_block_stats(best.get("blocks", []), stats)
        exported.append((pid, best))

    # Inject navigation using only the actually-exported page list
    exported_ids = [pid for pid, _ in exported]
    for i, (pid, best) in enumerate(exported):
        best["nav"] = {
            "prev": exported_ids[i - 1] if i > 0 else None,
            "next": exported_ids[i + 1] if i < len(exported_ids) - 1 else None,
            "parent_section": "",
        }
        (data_dir / f"render_page.{pid}.json").write_text(
            json.dumps(best, ensure_ascii=False, indent=2)
        )
        pages_meta.append(
            {
                "page_id": pid,
                "title": best.get("page", {}).get("title", ""),
            }
        )

    # Derive sections and page offset from TOC entries
    section_pids, page_offset = extract_toc_sections(data_dir, pages_meta)
    for pm in pages_meta:
        pm["depth"] = 0 if pm["page_id"] in section_pids else 1

    # Edition-scoped manifest, stamped with run provenance (S5U-869) so the
    # web side and reviewers can see which single run produced this bundle.
    manifest: dict = {"document_id": doc_id, "page_offset": page_offset, "pages": pages_meta}
    if provenance:
        manifest["provenance"] = provenance
    atomic_write_text(
        edition_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2),
    )
    print(f"  [{edition.upper()}] TOC sections: {len(section_pids)}, page_offset: {page_offset}")

    total = stats["headings"] + stats["paragraphs"] + stats["list_items"] + stats["figures"]
    print(f"  [{edition.upper()}] Exported {len(pages_meta)} pages, {total} blocks:")
    for k, v in stats.items():
        print(f"    {k}: {v}")


def export_glossary(
    doc_id: str,
    edition: str,
    glossary_path: Path | None,
    doc_public: Path,
    *,
    edition_dir: Path | None = None,
) -> None:
    """Export the run-bound glossary payload to the web bundle.

    ``glossary_path`` is resolved from the run's render result
    (``glossary_ref``). When the ref is set but the file is absent the caller has
    already refused (see :func:`_export_run.resolve_glossary_path`) — we never
    mtime-fall-back to a stray glossary from another run (S5U-869, fail-closed
    per G1).

    Stale-companion cleanup (S5U-892): when the bound run carries no glossary,
    any ``glossary.json`` from a prior run's export is removed (the reader
    fetches the fixed path unconditionally — a leftover is a cross-run splice),
    mirroring the ``render_page.*.json`` unlink in :func:`export_pages`. Under
    the S5U-890 staging build this unlink targets the (empty) staging dir, so the
    cleanup is a no-op there — the atomic swap of the whole edition dir discards
    the prior companions wholesale.

    ``edition_dir`` overrides the default ``doc_public / edition`` target for the
    two-phase staging build (S5U-890).
    """
    base_dir = doc_public / edition if edition_dir is None else edition_dir
    out = base_dir / "data"
    if glossary_path is None:
        # Remove a prior run's glossary.json (missing_ok: nothing to clean on a
        # fresh edition), else the reader splices it over this run's pages.
        (out / "glossary.json").unlink(missing_ok=True)
        print(f"  [{edition.upper()}] No glossary artifact for run, skipping")
        return
    data = json.loads(glossary_path.read_text())
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out / "glossary.json",
        json.dumps(data, ensure_ascii=False, indent=2),
    )
    print(f"  [{edition.upper()}] Exported glossary with {len(data.get('entries', []))} entries")
