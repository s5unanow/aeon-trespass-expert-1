"""Post-export validation checks for completeness, asset integrity, and title quality."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_REPO / "apps" / "pipeline" / "src"))

from _export_blocks import validate_figure_refs  # noqa: E402

from atr_pipeline.stages.render.page_builder import is_garbage_title  # noqa: E402

# S5U-699 — thresholds for the "facsimile mode but structured-payload exists"
# gate. Must refuse publishing a page that advertises presentation_mode=facsimile
# while the bundle still carries a substantial blocks list, unless an explicit
# config override has whitelisted the page (e.g. a truly image-dominant card
# reference where the fragments are noise). Chosen below the p0075/p0076 values
# (44/37 non-figure blocks, 943/1312 text chars) and above the quieter
# already-override-controlled facsimile pages (p0001=0 blocks, p0083=0 blocks).
# Using strict `>` so the boundary values themselves are documented as "OK".
_FACSIMILE_PAYLOAD_MAX_NON_FIGURE_BLOCKS = 10
_FACSIMILE_PAYLOAD_MAX_TEXT_CHARS = 400


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
            sm_id = page_data.get("source_map", {}).get("page_id", "")
            if sm_id and sm_id != pid:
                errors.append(
                    f"render_page.{pid}.json has source_map.page_id '{sm_id}' (expected '{pid}')"
                )
        except (json.JSONDecodeError, OSError, AttributeError):
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


def _count_text_chars(node: dict) -> int:
    """Count characters of all text leaves in a block subtree.

    Walks nested ``children`` arrays so that table / list / heading content
    whose text sits below the top level is still counted.
    """
    total = 0
    stack: list[dict] = [node]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        if n.get("kind") == "text":
            total += len(n.get("text", ""))
        for c in n.get("children", []):
            if isinstance(c, dict):
                stack.append(c)
    return total


def validate_presentation_mode_payload_consistency(
    data_dir: Path,
    facsimile_override_pids: Iterable[str],
) -> list[str]:
    """Refuse pages whose presentation_mode disagrees with their blocks payload.

    S5U-699 — enforces the Linear must-refuse bullets:
      * structured blocks exist but the page is forced to facsimile-only
      * the readable representation is only tiny raster text with no article
        mode
      * facsimile flag disagrees with the actual block payload

    A page is flagged when:
      * ``presentation_mode == "facsimile"``, AND
      * its blocks payload has *either* more than
        ``_FACSIMILE_PAYLOAD_MAX_NON_FIGURE_BLOCKS`` non-figure blocks OR
        more than ``_FACSIMILE_PAYLOAD_MAX_TEXT_CHARS`` characters of text
        across all blocks, AND
      * the page is not in the ``facsimile_override_pids`` allowlist.

    The allowlist is the set of page IDs that the document's TOML config has
    explicitly marked as ``presentation_mode = "facsimile"`` — a reviewer-
    visible, name-based list of genuine facsimile pages (G2 legitimate-
    override allowlist per ``.claude/rules/guards.md``). The block-payload
    signature is content-derived: any page matching it without an explicit
    override is blocked, so renames or new mis-classifications are caught
    without editing this file.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    allowed: set[str] = set(facsimile_override_pids)

    for render_file in sorted(data_dir.glob("render_page.*.json")):
        pid = render_file.stem.removeprefix("render_page.")
        try:
            page_data = json.loads(render_file.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"{pid}: presentation-mode guard could not read render file: {exc}")
            continue

        # Fail-closed at the schema boundary (S5U-699 Codex review #2):
        # a non-object root or a non-list `blocks` field must surface a
        # publish error, not bypass the guard. Guarding against both
        # silently-truthy shapes (e.g. lists, strings) and the falsy
        # `blocks == ""` / `blocks == 0` short-circuit that the previous
        # `or []` fallback would have swallowed.
        if not isinstance(page_data, dict):
            errors.append(
                f"{pid}: presentation-mode guard expected object-shaped "
                f"render payload, got {type(page_data).__name__}"
            )
            continue

        mode = page_data.get("presentation_mode")
        if mode != "facsimile":
            continue

        blocks = page_data.get("blocks", [])
        if not isinstance(blocks, list):
            errors.append(
                f"{pid}: presentation_mode=facsimile but blocks payload is "
                f"not a list (got {type(blocks).__name__})"
            )
            continue

        non_figure_count = sum(
            1 for b in blocks if isinstance(b, dict) and b.get("kind") != "figure"
        )
        text_chars = sum(_count_text_chars(b) for b in blocks if isinstance(b, dict))

        exceeds_blocks = non_figure_count > _FACSIMILE_PAYLOAD_MAX_NON_FIGURE_BLOCKS
        exceeds_chars = text_chars > _FACSIMILE_PAYLOAD_MAX_TEXT_CHARS
        if not (exceeds_blocks or exceeds_chars):
            continue

        if pid in allowed:
            continue

        errors.append(
            f"{pid}: presentation_mode=facsimile but payload has "
            f"{non_figure_count} non-figure blocks / {text_chars} text chars "
            f"(thresholds: >{_FACSIMILE_PAYLOAD_MAX_NON_FIGURE_BLOCKS} blocks "
            f"or >{_FACSIMILE_PAYLOAD_MAX_TEXT_CHARS} chars). Flip the page "
            f"to article mode, or add [render.page_overrides.{pid}] "
            f'presentation_mode = "facsimile" to the document config to '
            f"confirm the page is genuinely image-dominant."
        )

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
    facsimile_override_pids: Iterable[str] = (),
) -> bool:
    """Run all export validation checks. Returns True if no errors found.

    ``facsimile_override_pids`` is the set of page IDs explicitly marked as
    ``presentation_mode = "facsimile"`` by the document TOML config; it is
    consumed by the S5U-699 presentation-mode / payload consistency guard.
    """
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

    presentation_errors = validate_presentation_mode_payload_consistency(
        data_dir, facsimile_override_pids
    )
    for err in presentation_errors:
        print(f"  ERROR [{edition}]: {err}")
    if presentation_errors:
        ok = False

    title_warnings = validate_title_quality(pages_meta)
    for warn in title_warnings:
        print(f"  WARN [{edition}]: {warn}")
    # Title warnings don't block export — they are canary signals

    return ok
