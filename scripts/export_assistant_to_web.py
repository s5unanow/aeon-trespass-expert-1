#!/usr/bin/env python3
"""Export assistant artifacts (FTS5 index + manifest) to the web bundle.

Separate from export_to_web.py per architecture spec — assistant indexing
has its own responsibility boundary and should not grow the main export script.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
REPO = _SCRIPTS_DIR.parent

ARTIFACT_ROOT = REPO / "artifacts"
DOCUMENTS_ROOT = REPO / "apps" / "web" / "public" / "documents"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export assistant artifacts to web bundle")
    parser.add_argument("--doc", default="ato_core_v1_1", help="Document ID")
    parser.add_argument("--edition", choices=["en", "ru", "all"], default="all", help="Edition")
    return parser.parse_args(argv)


def _find_manifest(doc_id: str) -> dict | None:
    """Load the latest AssistantPackV1 manifest for a document."""
    manifest_dir = ARTIFACT_ROOT / doc_id / "assistant_pack.v1" / "document" / doc_id
    if not manifest_dir.exists():
        return None
    jsons = sorted(manifest_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not jsons:
        return None
    return json.loads(jsons[0].read_text())


def _find_index(doc_id: str, edition: str) -> Path | None:
    """Locate the assistant_index.sqlite for a document and edition."""
    index_path = (
        ARTIFACT_ROOT
        / doc_id
        / f"assistant_index.{edition}"
        / "document"
        / doc_id
        / "assistant_index.sqlite"
    )
    return index_path if index_path.exists() else None


def export_assistant(doc_id: str, edition: str) -> bool:
    """Export assistant artifacts for one edition. Returns True if artifacts were found."""
    index_path = _find_index(doc_id, edition)
    if index_path is None:
        print(f"  [{edition.upper()}] No assistant index found, skipping")
        return False

    data_dir = DOCUMENTS_ROOT / doc_id / edition / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    dest = data_dir / "assistant_index.sqlite"
    shutil.copy2(index_path, dest)
    size_kb = dest.stat().st_size / 1024
    print(f"  [{edition.upper()}] Exported assistant_index.sqlite ({size_kb:.1f} KB)")

    manifest = _find_manifest(doc_id)
    if manifest:
        (data_dir / "assistant_pack.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        count = manifest.get("chunks_count", "?")
        print(f"  [{edition.upper()}] Exported assistant_pack.json ({count} chunks)")

    return True


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    doc_id: str = args.doc
    editions = ["en", "ru"] if args.edition == "all" else [args.edition]

    print("Exporting assistant artifacts...")
    exported = 0
    for edition in editions:
        if export_assistant(doc_id, edition):
            exported += 1

    if exported:
        print(f"Done — exported assistant artifacts for {exported} edition(s).")
    else:
        print("No assistant artifacts found. Run the pipeline with chunk_export stage first.")


if __name__ == "__main__":
    main()
