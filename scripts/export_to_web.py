#!/usr/bin/env python3
"""Export pipeline artifacts to apps/web/public/documents/{doc_id}/{edition}/."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))

ARTIFACT_ROOT = REPO / "artifacts"
PDF_PATH = REPO / "materials" / "ATO_CORE_Rulebook_v1.1.pdf"


def score_render(data: dict, edition: str = "ru") -> int:
    """Score a render artifact — higher = better quality."""
    blocks = data.get("blocks", [])
    full = " ".join(
        c.get("text", "")
        for b in blocks[:3]
        for c in b.get("children", [])
        if c.get("kind") == "text"
    )
    has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in full)
    has_lists = any(b.get("kind") == "list_item" for b in blocks)
    has_marks = any(
        c.get("marks")
        for b in blocks
        for c in b.get("children", [])
        if c.get("kind") == "text" and c.get("marks")
    )
    lang_score = (0 if has_cyrillic else 100) if edition == "en" else (100 if has_cyrillic else 0)
    return lang_score + (10 if has_lists else 0) + (5 if has_marks else 0) + len(blocks)


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


DECORATIVE_PREFIXES = (
    "sym.board_tile",
    "sym.art_",
    "sym.terrain_",
    "sym.marker_",
    "sym.crown_",
    "sym.die_",
    "sym.titan_helmet",
)

_SENTENCE_RE = re.compile(r"(?<=\. )(?=[A-ZА-ЯЁ])")  # noqa: RUF001


def _text_content(block: dict) -> str:
    """Extract concatenated text from a block's children."""
    return "".join(c.get("text", "") for c in block.get("children", []) if c.get("kind") == "text")


def _postprocess_blocks(blocks: list[dict]) -> list[dict]:
    """Strip decorative icons, split long paragraphs, deduplicate."""
    result: list[dict] = []

    for block in blocks:
        # Strip decorative icons from children
        if "children" in block:
            block["children"] = [
                c
                for c in block["children"]
                if not (
                    c.get("kind") == "icon"
                    and c.get("symbol_id", "").startswith(DECORATIVE_PREFIXES)
                )
            ]

        # Split long paragraphs at sentence boundaries
        if block.get("kind") == "paragraph":
            text = _text_content(block)
            if len(text) > 600:
                parts = _split_paragraph(block)
                # Deduplicate before adding
                for part in parts:
                    if not _is_duplicate(result, part):
                        result.append(part)
                continue

        # Deduplicate
        if not _is_duplicate(result, block):
            result.append(block)

    return result


def _find_split_point(boundaries: list[int], max_chars: int) -> int | None:
    """Find the best sentence boundary to split at."""
    split_at = None
    for b in boundaries:
        if b <= max_chars:
            split_at = b
        else:
            break
    if split_at is None or split_at < 100:
        split_at = next((b for b in boundaries if b >= 100), None)
    return split_at


def _locate_split_child(children: list[dict], split_at: int) -> tuple[int | None, int | None]:
    """Find the child index and offset where text position falls."""
    char_count = 0
    for i, child in enumerate(children):
        if child.get("kind") != "text":
            continue
        child_text = child.get("text", "")
        if char_count + len(child_text) >= split_at:
            return i, split_at - char_count
        char_count += len(child_text)
    return None, None


def _split_paragraph(block: dict, max_chars: int = 600) -> list[dict]:
    """Split a paragraph block at sentence boundaries."""
    children = block.get("children", [])
    text = _text_content(block)
    if len(text) <= max_chars:
        return [block]

    boundaries = [m.start() for m in _SENTENCE_RE.finditer(text)]
    if not boundaries:
        return [block]

    split_at = _find_split_point(boundaries, max_chars)
    if split_at is None:
        return [block]

    split_idx, split_offset = _locate_split_child(children, split_at)
    if split_idx is None:
        return [block]

    first_children = children[:split_idx]
    remainder_children = children[split_idx:]

    split_child = remainder_children[0]
    if split_child.get("kind") == "text" and split_offset:
        text1 = split_child["text"][:split_offset]
        text2 = split_child["text"][split_offset:]
        if text1.strip():
            first_children.append({**split_child, "text": text1})
        if text2.strip():
            remainder_children = [{**split_child, "text": text2}, *remainder_children[1:]]
        else:
            remainder_children = remainder_children[1:]

    block1 = {**block, "id": f"{block['id']}.0", "children": first_children}
    block2 = {**block, "id": f"{block['id']}.1", "children": remainder_children}

    result = [block1]
    if len(_text_content(block2)) > max_chars:
        result.extend(_split_paragraph(block2, max_chars))
    else:
        result.append(block2)
    return result


def _is_duplicate(blocks: list[dict], block: dict) -> bool:
    """Check if block duplicates any recent block (within last 5)."""
    this_text = _text_content(block)[:80]
    if not this_text or len(this_text) < 3:
        return False
    for prev in blocks[-5:]:
        if prev.get("kind") != block.get("kind"):
            continue
        if _text_content(prev)[:80] == this_text:
            return True
    return False


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
        if b.get("kind") == "paragraph" and len(_text_content(b)) > 800:
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

    page_ids = sorted(d.name for d in render_src.iterdir() if d.is_dir())
    pages_meta = []
    stats = {"list_items": 0, "figures": 0, "headings": 0, "paragraphs": 0, "long_paras": 0}

    for i, pid in enumerate(page_ids):
        page_dir = render_src / pid
        jsons = list(page_dir.glob("*.json"))
        if not jsons:
            continue

        # Pick best render version (edition-aware scoring)
        best = None
        best_score = -1
        for j in jsons:
            data = json.loads(j.read_text())
            s = score_render(data, edition)
            if s > best_score:
                best = data
                best_score = s

        # Post-process blocks: strip decorative icons, split, deduplicate
        best["blocks"] = _postprocess_blocks(best.get("blocks", []))

        # Inject image figures if we have them
        imgs = page_images.get(pid, [])
        if imgs:
            figures = best.get("figures", {}) or {}
            for img in imgs:
                figures[img["asset_id"]] = {
                    "src": img["src"],
                    "alt": img["alt"],
                }
                has_fig = any(
                    b.get("kind") == "figure" and b.get("asset_id") == img["asset_id"]
                    for b in best.get("blocks", [])
                )
                if not has_fig:
                    best.setdefault("blocks", []).append(
                        {
                            "kind": "figure",
                            "id": f"{pid}.fig.{img['asset_id']}",
                            "asset_id": img["asset_id"],
                            "children": [],
                        }
                    )
            best["figures"] = figures

        # Navigation
        best["nav"] = {
            "prev": page_ids[i - 1] if i > 0 else None,
            "next": page_ids[i + 1] if i < len(page_ids) - 1 else None,
            "parent_section": "",
        }

        _count_block_stats(best.get("blocks", []), stats)

        (data_dir / f"render_page.{pid}.json").write_text(
            json.dumps(best, ensure_ascii=False, indent=2)
        )
        pages_meta.append(
            {
                "page_id": pid,
                "title": best.get("page", {}).get("title", ""),
            }
        )

    # Edition-scoped manifest
    (edition_dir / "manifest.json").write_text(
        json.dumps(
            {"document_id": doc_id, "pages": pages_meta},
            ensure_ascii=False,
            indent=2,
        )
    )

    total = stats["headings"] + stats["paragraphs"] + stats["list_items"] + stats["figures"]
    print(f"  [{edition.upper()}] Exported {len(pages_meta)} pages, {total} blocks:")
    for k, v in stats.items():
        print(f"    {k}: {v}")


def export_glossary(doc_id: str, edition: str, glossary_src: Path, doc_public: Path) -> None:
    """Export glossary payload to web bundle."""
    files = list(glossary_src.glob("*.json")) if glossary_src.exists() else []
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

    glossary_src = ARTIFACT_ROOT / doc_id / "glossary_payload.v1" / "document" / doc_id

    for edition in editions:
        print(f"Exporting {edition.upper()} render pages...")
        export_pages(doc_id, edition, render_src, doc_public, page_images)
        export_glossary(doc_id, edition, glossary_src, doc_public)

    write_document_index(documents_root)
    print("Done.")


if __name__ == "__main__":
    main()
