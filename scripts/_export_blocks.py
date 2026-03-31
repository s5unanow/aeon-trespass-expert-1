"""Block postprocessing helpers for export_to_web: split, deduplicate, strip icons."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

_SENTENCE_RE = re.compile(r"(?<=\. )(?=[A-ZА-ЯЁ])")  # noqa: RUF001
_BARE_ASSET_RE = re.compile(r"^img\d{4}$")

DECORATIVE_PREFIXES = (
    "sym.board_tile",
    "sym.art_",
    "sym.terrain_",
    "sym.marker_",
    "sym.crown_",
    "sym.die_",
    "sym.titan_helmet",
)


def text_content(block: dict) -> str:
    """Extract concatenated text from a block's children."""
    return "".join(c.get("text", "") for c in block.get("children", []) if c.get("kind") == "text")


def postprocess_blocks(blocks: list[dict]) -> list[dict]:
    """Strip decorative icons, split long paragraphs, deduplicate."""
    result: list[dict] = []

    for block in blocks:
        if "children" in block:
            block["children"] = [
                c
                for c in block["children"]
                if not (
                    c.get("kind") == "icon"
                    and c.get("symbol_id", "").startswith(DECORATIVE_PREFIXES)
                )
            ]

        if block.get("kind") == "paragraph":
            text = text_content(block)
            if len(text) > 600:
                for part in _split_paragraph(block):
                    if not _is_duplicate(result, part):
                        result.append(part)
                continue

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
    text = text_content(block)
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
    if len(text_content(block2)) > max_chars:
        result.extend(_split_paragraph(block2, max_chars))
    else:
        result.append(block2)
    return result


def _is_duplicate(blocks: list[dict], block: dict) -> bool:
    """Check if block duplicates any recent block (within last 5)."""
    this_text = text_content(block)[:80]
    if not this_text or len(this_text) < 3:
        return False
    for prev in blocks[-5:]:
        if prev.get("kind") != block.get("kind"):
            continue
        if text_content(prev)[:80] == this_text:
            return True
    return False


def rewrite_facsimile_urls(page_data: dict, doc_id: str) -> None:
    """Update facsimile raster URLs to web-public paths in place."""
    fac = page_data.get("facsimile")
    if not fac:
        return
    base = f"/documents/{doc_id}/rasters"
    for key in ("raster_src", "raster_src_hires"):
        val = fac.get(key)
        if val:
            fac[key] = f"{base}/{val.rsplit('/', 1)[-1]}"


def rewrite_figure_urls(page_data: dict, doc_id: str) -> int:
    """Rewrite pipeline-relative ``data/images/`` figure src paths to web-public paths.

    Returns the number of entries rewritten.
    """
    figures: dict = page_data.get("figures") or {}
    rewritten = 0
    prefix = "data/images/"
    web_base = f"/documents/{doc_id}/images"
    for entry in figures.values():
        src = entry.get("src", "")
        if src.startswith(prefix):
            entry["src"] = f"{web_base}/{src[len(prefix) :]}"
            rewritten += 1
    return rewritten


# Maximum figures injected per page.  Pages exceeding this threshold are
# typically dense reference/component pages where the facsimile view is
# more appropriate than dozens of stacked article-mode figures.
_MAX_INJECTED_FIGURES = 20


def inject_image_figures(
    page_data: dict,
    pid: str,
    imgs: list[dict],
) -> None:
    """Add image figure blocks and figure entries for article pages."""
    if not imgs:
        return
    figures = page_data.get("figures", {}) or {}
    existing_count = sum(1 for b in page_data.get("blocks", []) if b.get("kind") == "figure")
    budget = max(0, _MAX_INJECTED_FIGURES - existing_count)
    added = 0
    for img in imgs:
        has_fig = any(
            b.get("kind") == "figure" and b.get("asset_id") == img["asset_id"]
            for b in page_data.get("blocks", [])
        )
        if has_fig:
            # Already referenced — update src but don't count against budget
            figures[img["asset_id"]] = {"src": img["src"], "alt": img["alt"]}
            continue
        if added >= budget:
            continue
        figures[img["asset_id"]] = {"src": img["src"], "alt": img["alt"]}
        page_data.setdefault("blocks", []).append(
            {
                "kind": "figure",
                "id": f"{pid}.fig.{img['asset_id']}",
                "asset_id": img["asset_id"],
                "children": [],
            }
        )
        added += 1
    page_data["figures"] = figures


def namespace_bare_figures(page_data: dict, pid: str) -> int:
    """Rewrite bare ``imgNNNN`` asset IDs to ``{pid}.imgNNNN`` in place.

    Handles legacy render artifacts produced before asset-ID namespacing.
    Returns the number of entries rewritten.
    """
    figures: dict = page_data.get("figures") or {}
    rewritten = 0

    # Rewrite figures dict keys and fix self-referencing src values
    bare_keys = [k for k in figures if _BARE_ASSET_RE.match(k)]
    for bare in bare_keys:
        namespaced = f"{pid}.{bare}"
        if namespaced not in figures:
            entry = figures[bare]
            # Fix self-referencing src (e.g. "src": "img0000" -> drop it;
            # inject_image_figures will populate a valid src later)
            if _BARE_ASSET_RE.match(entry.get("src", "")):
                entry["src"] = ""
            figures[namespaced] = entry
        del figures[bare]
        rewritten += 1

    # Rewrite asset_id in figure blocks
    for block in page_data.get("blocks", []):
        if block.get("kind") == "figure" and _BARE_ASSET_RE.match(block.get("asset_id", "")):
            block["asset_id"] = f"{pid}.{block['asset_id']}"
            rewritten += 1

    page_data["figures"] = figures
    return rewritten


def validate_figure_refs(page_data: dict, pid: str) -> list[str]:
    """Check that every figure block resolves to a valid figures entry.

    Returns a list of error messages (empty = valid).
    """
    figures: dict = page_data.get("figures") or {}
    errors: list[str] = []
    for block in page_data.get("blocks", []):
        if block.get("kind") != "figure":
            continue
        aid = block.get("asset_id", "")
        if aid not in figures:
            errors.append(f"{pid}: figure block references missing asset '{aid}'")
        elif _BARE_ASSET_RE.match(figures[aid].get("src", "")):
            errors.append(f"{pid}: figure '{aid}' has bare src '{figures[aid]['src']}'")
    return errors


def export_facsimile_rasters(
    doc_id: str,
    doc_public: Path,
    artifact_root: Path,
    facsimile_page_ids: list[str],
) -> None:
    """Copy rasters for facsimile pages to web public directory."""
    if not facsimile_page_ids:
        return
    rasters_dir = doc_public / "rasters"
    rasters_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    # Prefer release bundle rasters
    release_rasters = artifact_root / doc_id / "release" / "rasters"

    for pid in facsimile_page_ids:
        for dpi in (150, 300):
            fname = f"{pid}__{dpi}dpi.png"
            if release_rasters.exists():
                src = release_rasters / fname
                if src.exists():
                    shutil.copy2(src, rasters_dir / fname)
                    copied += 1
                    continue

            # Fallback: resolve from raster_meta.v1
            meta_dir = artifact_root / doc_id / "raster_meta.v1" / "page" / pid
            if not meta_dir.exists():
                continue
            meta_files = sorted(meta_dir.glob("*.json"))
            if not meta_files:
                continue
            meta = json.loads(meta_files[-1].read_text())
            for level in meta.get("levels", []):
                if level.get("dpi") == dpi:
                    src = artifact_root / level["relative_path"]
                    if src.exists():
                        shutil.copy2(src, rasters_dir / fname)
                        copied += 1

    print(f"  Copied {copied} raster files for {len(facsimile_page_ids)} facsimile pages")
