#!/usr/bin/env python3
"""Export pipeline artifacts to the web viewer public directory.

Picks the best render version per page (Russian + marks + list items preferred),
populates prev/next navigation, extracts embedded images from the source PDF,
and writes everything to apps/web/public/documents/{doc_id}/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))

DOC_ID = "ato_core_v1_1"
ARTIFACT_ROOT = REPO / "artifacts"
WEB_PUBLIC = REPO / "apps" / "web" / "public" / "documents" / DOC_ID
RENDER_SRC = ARTIFACT_ROOT / DOC_ID / "render_page.v1" / "page"
PDF_PATH = REPO / "materials" / "ATO_CORE_Rulebook_v1.1.pdf"


def score_render(data: dict) -> int:
    """Score a render artifact — higher = better quality."""
    blocks = data.get("blocks", [])
    texts = [
        c.get("text", "")
        for b in blocks[:3]
        for c in b.get("children", [])
        if c.get("kind") == "text"
    ]
    full = " ".join(texts)
    has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in full)
    has_lists = any(b.get("kind") == "list_item" for b in blocks)
    has_marks = any(
        c.get("marks")
        for b in blocks
        for c in b.get("children", [])
        if c.get("kind") == "text" and c.get("marks")
    )
    return (
        (100 if has_cyrillic else 0)
        + (10 if has_lists else 0)
        + (5 if has_marks else 0)
        + len(blocks)
    )


def extract_images() -> dict[str, list[dict]]:
    """Extract significant images from the PDF, save to web public, return per-page map."""
    if not PDF_PATH.exists():
        print(f"  PDF not found at {PDF_PATH}, skipping image extraction")
        return {}

    from atr_pipeline.services.pdf.image_extractor import extract_page_images

    img_dir = WEB_PUBLIC / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    page_images: dict[str, list[dict]] = {}
    total = 0

    for pnum in range(1, 84):
        pid = f"p{pnum:04d}"
        try:
            images = extract_page_images(
                PDF_PATH, page_number=pnum, min_width=100, min_height=100,
            )
        except Exception as e:
            print(f"  WARN: image extraction failed for {pid}: {e}")
            continue

        if not images:
            continue

        page_images[pid] = []
        for img in images:
            fname = f"{img.image_id}{img.extension}"
            (img_dir / fname).write_bytes(img.image_bytes)
            page_images[pid].append({
                "asset_id": img.image_id,
                "src": f"/documents/{DOC_ID}/images/{fname}",
                "alt": img.image_id,
                "width": img.width_px,
                "height": img.height_px,
            })
            total += 1

    print(f"  Extracted {total} images across {len(page_images)} pages")
    return page_images


def export_pages(page_images: dict[str, list[dict]]) -> None:
    """Export render pages with navigation and image figures."""
    data_dir = WEB_PUBLIC / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    page_ids = sorted(d.name for d in RENDER_SRC.iterdir() if d.is_dir())
    pages_meta = []
    stats = {
        "list_items": 0, "figures": 0, "headings": 0,
        "paragraphs": 0, "long_paras": 0,
    }

    for i, pid in enumerate(page_ids):
        page_dir = RENDER_SRC / pid
        jsons = list(page_dir.glob("*.json"))
        if not jsons:
            continue

        # Pick best render version
        best = None
        best_score = -1
        for j in jsons:
            data = json.loads(j.read_text())
            s = score_render(data)
            if s > best_score:
                best = data
                best_score = s

        # Inject image figures if we have them
        imgs = page_images.get(pid, [])
        if imgs:
            figures = best.get("figures", {}) or {}
            for img in imgs:
                figures[img["asset_id"]] = {
                    "src": img["src"],
                    "alt": img["alt"],
                }
                # Add figure block if not already present
                has_fig = any(
                    b.get("kind") == "figure" and b.get("asset_id") == img["asset_id"]
                    for b in best.get("blocks", [])
                )
                if not has_fig:
                    best.setdefault("blocks", []).append({
                        "kind": "figure",
                        "id": f"{pid}.fig.{img['asset_id']}",
                        "asset_id": img["asset_id"],
                        "children": [],
                    })
            best["figures"] = figures

        # Navigation
        best["nav"] = {
            "prev": page_ids[i - 1] if i > 0 else None,
            "next": page_ids[i + 1] if i < len(page_ids) - 1 else None,
            "parent_section": "",
        }

        # Stats
        for b in best.get("blocks", []):
            k = b.get("kind", "")
            if k == "list_item":
                stats["list_items"] += 1
            elif k == "figure":
                stats["figures"] += 1
            elif k == "heading":
                stats["headings"] += 1
            elif k == "paragraph":
                stats["paragraphs"] += 1
                text_len = len("".join(
                    c.get("text", "")
                    for c in b.get("children", [])
                    if c.get("kind") == "text"
                ))
                if text_len > 800:
                    stats["long_paras"] += 1

        (data_dir / f"render_page.{pid}.json").write_text(
            json.dumps(best, ensure_ascii=False, indent=2)
        )
        pages_meta.append({
            "page_id": pid,
            "title": best.get("page", {}).get("title", ""),
        })

    # Manifest
    (WEB_PUBLIC / "manifest.json").write_text(
        json.dumps(
            {"document_id": DOC_ID, "pages": pages_meta},
            ensure_ascii=False, indent=2,
        )
    )

    total = stats["headings"] + stats["paragraphs"] + stats["list_items"] + stats["figures"]
    print(f"  Exported {len(pages_meta)} pages, {total} blocks:")
    for k, v in stats.items():
        print(f"    {k}: {v}")


def main() -> None:
    print("Extracting images from PDF...")
    page_images = extract_images()
    print("Exporting render pages...")
    export_pages(page_images)
    print("Done.")


if __name__ == "__main__":
    main()
