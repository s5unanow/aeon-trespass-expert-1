"""Post-export validation checks for completeness, asset integrity, and title quality."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_REPO / "apps" / "pipeline" / "src"))

from _export_blocks import validate_figure_refs  # noqa: E402

from atr_pipeline.stages.render.page_builder import is_garbage_title  # noqa: E402


def validate_export_completeness(
    data_dir: Path,
    pages_meta: list[dict],
) -> list[str]:
    """Check that manifest pages and render files are in sync.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    manifest_ids = {pm["page_id"] for pm in pages_meta}
    render_files = {
        f.stem.removeprefix("render_page.") for f in data_dir.glob("render_page.*.json")
    }

    missing_render = manifest_ids - render_files
    for pid in sorted(missing_render):
        errors.append(f"manifest advertises '{pid}' but render_page.{pid}.json is missing")

    orphan_render = render_files - manifest_ids
    for pid in sorted(orphan_render):
        errors.append(f"render_page.{pid}.json exists but is not in manifest")

    # Verify internal page.id matches filename-derived ID
    for pid in sorted(render_files & manifest_ids):
        render_path = data_dir / f"render_page.{pid}.json"
        try:
            page_data = json.loads(render_path.read_text())
            internal_id = page_data.get("page", {}).get("id", "")
            if internal_id and internal_id != pid:
                errors.append(
                    f"render_page.{pid}.json has internal page.id "
                    f"'{internal_id}' (expected '{pid}')"
                )
        except (json.JSONDecodeError, OSError):
            errors.append(f"render_page.{pid}.json could not be read for internal ID check")

    return errors


def validate_asset_existence(data_dir: Path) -> list[str]:
    """Check that figure src paths in render pages resolve to existing files.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    doc_public = data_dir.parent.parent  # .../documents/doc_id

    for render_file in sorted(data_dir.glob("render_page.*.json")):
        pid = render_file.stem.removeprefix("render_page.")
        page_data = json.loads(render_file.read_text())

        # Reuse existing figure-ref validation from _export_blocks
        for err in validate_figure_refs(page_data, pid):
            errors.append(err)

        # Check that figure src files actually exist on disk
        figures: dict = page_data.get("figures") or {}
        for aid, fig in figures.items():
            src = fig.get("src", "")
            if not src or src == aid:
                continue
            # src paths are relative to web public root: /documents/...
            if src.startswith("/documents/"):
                asset_path = doc_public.parent.parent / src.lstrip("/")
                if not asset_path.exists():
                    errors.append(f"{pid}: figure '{aid}' src '{src}' not found on disk")

    return errors


def validate_title_quality(pages_meta: list[dict]) -> list[str]:
    """Warn on any remaining garbage titles in the manifest.

    Returns warnings (not hard errors) as a regression canary.
    """
    warnings: list[str] = []
    for pm in pages_meta:
        title = pm.get("title", "")
        if is_garbage_title(title):
            warnings.append(f"{pm['page_id']}: garbage title '{title}'")
    return warnings


def run_export_validation(
    edition_dir: Path,
    pages_meta: list[dict],
) -> bool:
    """Run all export validation checks. Returns True if no errors found."""
    data_dir = edition_dir / "data"
    edition = edition_dir.name.upper()
    ok = True

    completeness_errors = validate_export_completeness(data_dir, pages_meta)
    for err in completeness_errors:
        print(f"  ERROR [{edition}]: {err}")
    if completeness_errors:
        ok = False

    asset_errors = validate_asset_existence(data_dir)
    for err in asset_errors:
        print(f"  ERROR [{edition}]: {err}")
    if asset_errors:
        ok = False

    title_warnings = validate_title_quality(pages_meta)
    for warn in title_warnings:
        print(f"  WARN [{edition}]: {warn}")
    # Title warnings don't block export — they are canary signals

    return ok
