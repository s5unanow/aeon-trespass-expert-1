#!/usr/bin/env python3
"""Export pipeline artifacts to apps/web/public/documents/{doc_id}/{edition}/."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
REPO = _SCRIPTS_DIR.parent
sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
sys.path.insert(0, str(_SCRIPTS_DIR))

from _export_blocks import (  # noqa: E402
    export_facsimile_rasters,
    inject_image_figures,
    namespace_bare_figures,
    postprocess_blocks,
    rewrite_facsimile_urls,
    rewrite_figure_urls,
    text_content,
)
from _export_images import extract_images, resolve_source_pdf  # noqa: E402
from _export_qa import export_qa  # noqa: E402
from _export_run import (  # noqa: E402
    ResolvedRun,
    RunResolutionError,
    load_run_pages,
    resolve_glossary_path,
    resolve_qa_summary_path,
    resolve_run,
)
from _export_validation import run_export_validation  # noqa: E402

from atr_pipeline.config import load_document_config  # noqa: E402
from atr_pipeline.store.atomic_write import atomic_write_text  # noqa: E402

logger = logging.getLogger(__name__)

# Re-exports for S5U-688 regression tests and downstream callers that want to
# import the helpers from the main entry script.
__all__ = ["extract_images", "resolve_source_pdf"]

ARTIFACT_ROOT = REPO / "artifacts"
REGISTRY_PATH = REPO / "var" / "registry.db"


_TOC_ENTRY_RE = re.compile(r"(.+?)\.{3,}\s*(\d+)")


def _parse_toc_entries(data_dir: Path) -> list[tuple[str, int]]:
    """Extract (title, printed_page_number) pairs from TOC paragraphs."""
    entries: list[tuple[str, int]] = []
    for render_file in sorted(data_dir.glob("render_page.*.json")):
        page_data = json.loads(render_file.read_text())
        for block in page_data.get("blocks", []):
            if block.get("kind") != "paragraph":
                continue
            matches = _TOC_ENTRY_RE.findall(text_content(block))
            if len(matches) >= 2:
                entries.extend((t.strip(), int(n)) for t, n in matches)
    return entries


def _match_toc_by_title(
    toc_entries: list[tuple[str, int]], pages_meta: list[dict]
) -> tuple[set[str], int]:
    """Match TOC entries to pages by normalized title; return (section_pids, offset)."""
    title_lookup: dict[str, tuple[str, int]] = {}
    for pm in pages_meta:
        title = pm.get("title", "").strip().lower()
        if title:
            title_lookup[title] = (pm["page_id"], int(pm["page_id"].lstrip("p")))

    section_pids: set[str] = set()
    offset = 0
    for title, printed_num in toc_entries:
        match = title_lookup.get(title.lower())
        if match:
            if not section_pids:
                offset = match[1] - printed_num
            section_pids.add(match[0])
    return section_pids, offset


def _extract_toc_sections(data_dir: Path, pages_meta: list[dict]) -> tuple[set[str], int]:
    """Parse TOC, match to manifest pages, return (section_page_ids, page_offset)."""
    toc_entries = _parse_toc_entries(data_dir)
    if not toc_entries:
        return set(), 0

    section_pids, offset = _match_toc_by_title(toc_entries, pages_meta)
    if section_pids:
        return section_pids, offset

    # Fallback: titles differ (e.g. translated) — try candidate offsets by page number
    titled_pids = {pm["page_id"] for pm in pages_meta if pm.get("title", "").strip()}
    for candidate in range(4):
        matched = {f"p{n + candidate:04d}" for _, n in toc_entries}
        if matched <= titled_pids:
            return matched, candidate

    return set(), 0


_KIND_MAP = {
    "list_item": "list_items",
    "figure": "figures",
    "heading": "headings",
    "paragraph": "paragraphs",
}


def _load_facsimile_override_pids(doc_id: str) -> list[str]:
    """Load the allowlist of page IDs explicitly marked ``presentation_mode = "facsimile"``.

    Consumed by the S5U-699 publish-time consistency guard in
    ``_export_validation.validate_presentation_mode_payload_consistency``.
    A page appearing in this list is intentionally image-dominant even if
    its blocks payload is substantial (e.g. p0006/p0007 — card-component
    overview pages with dense caption fragments that are meaningful only
    alongside the raster). Pages *not* in this list whose payload still
    advertises facsimile mode while carrying many structured blocks are
    rejected at publish time.

    The allowlist is derived from the **same merged/validated
    ``DocumentBuildConfig``** the render stage consumes (base.toml + env
    overlay + document TOML, validated by pydantic) so the export gate
    cannot drift from the pipeline's classification contract. See the
    S5U-699 Codex review for the contract-split regression this guards
    against.

    Returns a sorted list for deterministic logging.
    """
    config = load_document_config(doc_id)
    return sorted(
        pid
        for pid, override in config.render.page_overrides.items()
        if override.presentation_mode == "facsimile"
    )


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
) -> None:
    """Export ref-bound render pages with navigation and image figures.

    ``render_pages`` maps page_id → already-resolved render-page payload,
    selected from a single pipeline run (S5U-869) rather than picked by mtime.
    All artifact selection happens upstream in ``_export_run.resolve_run`` so
    this function only transforms + writes; it never enumerates the artifact
    store or chooses between competing artifacts.
    """
    edition_dir = doc_public / edition
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
    section_pids, page_offset = _extract_toc_sections(data_dir, pages_meta)
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
    doc_id: str, edition: str, glossary_path: Path | None, doc_public: Path
) -> None:
    """Export the run-bound glossary payload to the web bundle.

    ``glossary_path`` is resolved from the run's render result
    (``glossary_ref``). When the run carries no glossary ref the export skips
    cleanly. When the ref is set but the file is absent the caller has already
    refused (see :func:`_resolve_glossary_path`) — we never mtime-fall-back to
    a stray glossary from another run (S5U-869, fail-closed per guards.md G1).
    """
    if glossary_path is None:
        print(f"  [{edition.upper()}] No glossary artifact for run, skipping")
        return
    data = json.loads(glossary_path.read_text())
    out = doc_public / edition / "data"
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out / "glossary.json",
        json.dumps(data, ensure_ascii=False, indent=2),
    )
    print(f"  [{edition.upper()}] Exported glossary with {len(data.get('entries', []))} entries")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export pipeline artifacts to web viewer")
    parser.add_argument("--doc", default="ato_core_v1_1", help="Document ID")
    parser.add_argument("--edition", choices=["en", "ru", "all"], default="all", help="Edition")
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Pin export to a specific complete run (default: latest complete run "
            "for the document/edition). Refuses if the run is missing or unfinished."
        ),
    )
    return parser.parse_args(argv)


def _build_document_index(documents_root: Path) -> list[dict]:
    """Scan documents directory and return list of {document_id, editions}."""
    if not documents_root.exists():
        return []
    entries: list[dict] = []
    for doc_dir in sorted(documents_root.iterdir()):
        if not doc_dir.is_dir() or doc_dir.name.startswith("."):
            continue
        editions = sorted(
            d.name for d in doc_dir.iterdir() if d.is_dir() and (d / "manifest.json").exists()
        )
        if editions:
            entries.append({"document_id": doc_dir.name, "editions": editions})
        elif (doc_dir / "manifest.json").exists():
            # Root-level-only manifest — synthetic "default" edition for loadManifest() fallback
            entries.append({"document_id": doc_dir.name, "editions": ["default"]})
    return entries


def write_document_index(documents_root: Path) -> None:
    """Write /documents/index.json listing all exported documents and editions."""
    entries = _build_document_index(documents_root)
    (documents_root / "index.json").write_text(
        json.dumps({"documents": entries}, ensure_ascii=False, indent=2)
    )
    print(f"Wrote document index: {len(entries)} document(s)")


def _export_edition(
    doc_id: str,
    edition: str,
    resolved: ResolvedRun,
    doc_public: Path,
    page_images: dict[str, list[dict]],
    facsimile_override_pids: list[str],
) -> bool:
    """Export one edition's bundle from a single resolved run. Returns validation OK."""
    print(f"Exporting {edition.upper()} render pages from run {resolved.run_id}...")
    render_pages = load_run_pages(resolved, ARTIFACT_ROOT)

    facsimile_pids = [
        pid for pid, data in render_pages.items() if data.get("presentation_mode") == "facsimile"
    ]
    if facsimile_pids:
        print(f"  Exporting rasters for {len(facsimile_pids)} facsimile pages...")
        export_facsimile_rasters(doc_id, doc_public, ARTIFACT_ROOT, sorted(facsimile_pids))

    export_pages(doc_id, edition, render_pages, doc_public, page_images, resolved.provenance())
    export_glossary(doc_id, edition, resolve_glossary_path(resolved, ARTIFACT_ROOT), doc_public)
    export_qa(
        ARTIFACT_ROOT,
        doc_id,
        edition,
        doc_public,
        summary_path=resolve_qa_summary_path(resolved, ARTIFACT_ROOT),
        ref_bound=True,
    )

    edition_dir = doc_public / edition
    manifest = json.loads((edition_dir / "manifest.json").read_text())
    return run_export_validation(edition_dir, manifest["pages"], facsimile_override_pids)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    doc_id: str = args.doc
    run_id: str | None = args.run_id
    editions = ["en", "ru"] if args.edition == "all" else [args.edition]

    documents_root = REPO / "apps" / "web" / "public" / "documents"
    doc_public = documents_root / doc_id

    print("Extracting images from PDF...")
    page_images = extract_images(doc_id, doc_public, repo_root=REPO)

    facsimile_override_pids = _load_facsimile_override_pids(doc_id)
    if facsimile_override_pids:
        print(f"Config-allowlisted facsimile pages: {', '.join(facsimile_override_pids)}")

    validation_ok = True
    try:
        for edition in editions:
            # Ref-bind each edition to a single complete run (S5U-869): an
            # explicit --run-id pins the exact run; otherwise the latest
            # complete run for this document/edition is used. Every artifact
            # comes from that one run — no mtime selection, no cross-run splice.
            resolved = resolve_run(
                REGISTRY_PATH,
                doc_id,
                artifact_root=ARTIFACT_ROOT,
                run_id=run_id,
                edition=edition,
            )
            if not _export_edition(
                doc_id, edition, resolved, doc_public, page_images, facsimile_override_pids
            ):
                validation_ok = False
    except RunResolutionError as exc:
        print(f"Export refused: {exc}")
        sys.exit(1)

    write_document_index(documents_root)
    if not validation_ok:
        print("Export validation FAILED — see errors above.")
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
