#!/usr/bin/env python3
"""Export pipeline artifacts to apps/web/public/documents/{doc_id}/{edition}/."""

from __future__ import annotations

import argparse
import json
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
    postprocess_blocks,
    rewrite_facsimile_urls,
    text_content,
)

ARTIFACT_ROOT = REPO / "artifacts"
PDF_PATH = REPO / "materials" / "ATO_CORE_Rulebook_v1.1.pdf"


def _pick_latest(jsons: list[Path], edition: str = "") -> dict | None:
    """Load the newest artifact whose ``document_version`` matches *edition*.

    Selection follows two tiers when *edition* is non-empty:

    1. **Exact match** — ``document_version == edition``.
    2. **Untagged fallback** — ``document_version == ""``, used only when *no*
       tagged artifacts exist in the candidate set.  This preserves backwards
       compatibility for pages that predate edition tagging (S5U-402) while
       preventing cross-edition contamination when a tagged artifact for a
       *different* edition proves the page has edition-specific content.

    When *edition* is empty all artifacts are eligible (no filtering).

    Returns the parsed JSON dict of the winning artifact, or ``None`` when
    no artifact matches the requested edition.
    """
    best_exact: dict | None = None
    best_exact_mtime: float = 0.0
    best_untagged: dict | None = None
    best_untagged_mtime: float = 0.0
    has_any_tagged = False

    for p in jsons:
        mt = p.stat().st_mtime
        data = json.loads(p.read_text())
        dv = data.get("document_version", "")

        if edition == "":
            # No specific edition requested — accept everything.
            if mt > best_exact_mtime:
                best_exact = data
                best_exact_mtime = mt
        elif dv == edition:
            if mt > best_exact_mtime:
                best_exact = data
                best_exact_mtime = mt
        elif dv != "":
            has_any_tagged = True
        elif mt > best_untagged_mtime:
            # dv == "" and edition != ""
            best_untagged = data
            best_untagged_mtime = mt

    if best_exact is not None:
        return best_exact

    # Fall back to untagged artifacts only when no tagged artifacts exist
    # at all for this page — avoids picking stale pre-tagging artifacts
    # whose actual edition is unknown.
    if not has_any_tagged:
        return best_untagged

    return None


def extract_images(doc_id: str, doc_public: Path) -> dict[str, list[dict]]:
    """Extract images from PDF and save to web public dir."""
    if not PDF_PATH.exists():
        print(f"  PDF not found at {PDF_PATH}, skipping image extraction")
        return {}
    from atr_pipeline.services.pdf.image_extractor import extract_page_images

    img_dir = doc_public / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    page_images: dict[str, list[dict]] = {}
    total = 0
    for pnum in range(1, 84):
        pid = f"p{pnum:04d}"
        try:
            images = extract_page_images(PDF_PATH, page_number=pnum, min_width=100, min_height=100)
        except Exception as e:
            print(f"  WARN: image extraction failed for {pid}: {e}")
            continue
        if not images:
            continue
        page_images[pid] = []
        for img in images:
            fname = f"{img.image_id}{img.extension}"
            (img_dir / fname).write_bytes(img.image_bytes)
            page_images[pid].append(
                {
                    "asset_id": img.image_id,
                    "src": f"/documents/{doc_id}/images/{fname}",
                    "alt": img.image_id,
                    "width": img.width_px,
                    "height": img.height_px,
                }
            )
            total += 1
    print(f"  Extracted {total} images across {len(page_images)} pages")
    return page_images


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
    render_src: Path,
    doc_public: Path,
    page_images: dict[str, list[dict]],
) -> None:
    """Export render pages with navigation and image figures."""
    edition_dir = doc_public / edition
    data_dir = edition_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale render_page files from prior exports
    for stale in data_dir.glob("render_page.*.json"):
        stale.unlink()

    all_page_ids = sorted(d.name for d in render_src.iterdir() if d.is_dir())
    exported: list[tuple[str, dict]] = []  # (page_id, data) for exported pages
    pages_meta = []
    stats = {"list_items": 0, "figures": 0, "headings": 0, "paragraphs": 0, "long_paras": 0}

    for pid in all_page_ids:
        page_dir = render_src / pid
        jsons = list(page_dir.glob("*.json"))
        if not jsons:
            continue

        # Pick the latest artifact matching this edition — the most recent
        # pipeline run always has the best quality (filtered annotations, etc.).
        best = _pick_latest(jsons, edition)
        if best is None:
            continue

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

    # Edition-scoped manifest
    manifest = {"document_id": doc_id, "page_offset": page_offset, "pages": pages_meta}
    (edition_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"  [{edition.upper()}] TOC sections: {len(section_pids)}, page_offset: {page_offset}")

    total = stats["headings"] + stats["paragraphs"] + stats["list_items"] + stats["figures"]
    print(f"  [{edition.upper()}] Exported {len(pages_meta)} pages, {total} blocks:")
    for k, v in stats.items():
        print(f"    {k}: {v}")


def export_glossary(doc_id: str, edition: str, glossary_src: Path, doc_public: Path) -> None:
    """Export glossary payload to web bundle (same glossary for all editions)."""
    files = sorted(glossary_src.glob("*.json")) if glossary_src.exists() else []
    if not files:
        print(f"  [{edition.upper()}] No glossary artifact found, skipping")
        return
    data = json.loads(files[0].read_text())
    out = doc_public / edition / "data"
    out.mkdir(parents=True, exist_ok=True)
    (out / "glossary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  [{edition.upper()}] Exported glossary with {len(data.get('entries', []))} entries")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export pipeline artifacts to web viewer")
    parser.add_argument("--doc", default="ato_core_v1_1", help="Document ID")
    parser.add_argument("--edition", choices=["en", "ru", "all"], default="all", help="Edition")
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


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    doc_id: str = args.doc
    editions = ["en", "ru"] if args.edition == "all" else [args.edition]

    render_src = ARTIFACT_ROOT / doc_id / "render_page.v1" / "page"
    documents_root = REPO / "apps" / "web" / "public" / "documents"
    doc_public = documents_root / doc_id

    if not render_src.exists():
        print(f"No render artifacts found at {render_src}")
        sys.exit(1)

    print("Extracting images from PDF...")
    page_images = extract_images(doc_id, doc_public)

    # Collect facsimile page IDs from render artifacts
    facsimile_pids: list[str] = []
    for pid_dir in sorted(render_src.iterdir()):
        if not pid_dir.is_dir():
            continue
        if any(
            json.loads(jf.read_text()).get("presentation_mode") == "facsimile"
            for jf in pid_dir.glob("*.json")
        ):
            facsimile_pids.append(pid_dir.name)

    if facsimile_pids:
        print(f"Exporting rasters for {len(facsimile_pids)} facsimile pages...")
        export_facsimile_rasters(doc_id, doc_public, ARTIFACT_ROOT, facsimile_pids)

    glossary_src = ARTIFACT_ROOT / doc_id / "glossary_payload.v1" / "document" / doc_id

    for edition in editions:
        print(f"Exporting {edition.upper()} render pages...")
        export_pages(doc_id, edition, render_src, doc_public, page_images)
        export_glossary(doc_id, edition, glossary_src, doc_public)

    write_document_index(documents_root)
    print("Done.")


if __name__ == "__main__":
    main()
