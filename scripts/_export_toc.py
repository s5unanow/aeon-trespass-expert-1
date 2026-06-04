"""TOC parsing + section/offset derivation for the web export.

Extracted verbatim from ``export_to_web`` (S5U-870) so the entry script stays
within the 400-line file-length budget once the blocking-QA gate wiring landed.
Pure functions over already-exported render pages — no I/O beyond reading the
``render_page.*.json`` files the exporter just wrote, and no behavior change.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from _export_blocks import text_content

_TOC_ENTRY_RE = re.compile(r"(.+?)\.{3,}\s*(\d+)")


def parse_toc_entries(data_dir: Path) -> list[tuple[str, int]]:
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


def match_toc_by_title(
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


def extract_toc_sections(data_dir: Path, pages_meta: list[dict]) -> tuple[set[str], int]:
    """Parse TOC, match to manifest pages, return (section_page_ids, page_offset)."""
    toc_entries = parse_toc_entries(data_dir)
    if not toc_entries:
        return set(), 0

    section_pids, offset = match_toc_by_title(toc_entries, pages_meta)
    if section_pids:
        return section_pids, offset

    # Fallback: titles differ (e.g. translated) — try candidate offsets by page number
    titled_pids = {pm["page_id"] for pm in pages_meta if pm.get("title", "").strip()}
    for candidate in range(4):
        matched = {f"p{n + candidate:04d}" for _, n in toc_entries}
        if matched <= titled_pids:
            return matched, candidate

    return set(), 0
