"""Source-PDF resolution and per-page image extraction for web export.

Lives outside ``export_to_web.py`` so the main script stays under the
repo's 400-line ceiling (S5U-688).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from _export_run import RunResolutionError

logger = logging.getLogger(__name__)


def verify_source_pdf_sha(
    doc_id: str,
    expected_shas: Iterable[str],
    *,
    repo_root: Path | None = None,
) -> None:
    """Refuse if the on-disk source PDF differs from the resolved run(s) (S5U-889).

    ``extract_images`` re-reads the configured source PDF run-agnostically, so a
    PDF swapped between the bound run and the export would splice images from a
    PDF the run never rendered against (the S5U-889 cross-source hazard). The
    resolved run records ``source_pdf_sha256`` precisely to enable this binding
    check; this function enforces it before any image is extracted.

    Fail-closed contract (guards.md Rule G1): if the on-disk PDF exists and its
    sha256 differs from a recorded ``source_pdf_sha256``, raise
    :class:`RunResolutionError` (the exporter turns that into a clean non-zero
    "Export refused" exit). The sha is computed with the *same* helper the
    ingest stage used to record it (``atr_pipeline.utils.hashing.sha256_file``),
    so equal bytes always match.

    Two cases are intentionally *not* refused (neither is a splice hazard, and
    refusing would break legitimate workflows):

    * **PDF absent on disk** — ``extract_images`` already skips extraction and
      emits ``{}``; no images are spliced from a wrong PDF. Common in CI / lite
      clones that omit the source PDF (see ``test_extract_images_ato_default``).
    * **Recorded sha empty** — a legacy run predating ``source_pdf_sha256``
      capture cannot be verified; skip with a warning rather than refusing every
      historical run (mirrors the S5U-888 legacy-summary handling).
    """
    from atr_pipeline.utils.hashing import sha256_file

    pdf_path, page_count = resolve_source_pdf(doc_id, repo_root=repo_root)
    if page_count == 0:
        # PDF not on disk: extract_images will skip; nothing to bind against.
        return
    recorded = {sha for sha in expected_shas if sha}
    if not recorded:
        logger.warning(
            "No recorded source_pdf_sha256 for %s (legacy run); skipping on-disk PDF binding check",
            doc_id,
        )
        return
    on_disk = sha256_file(pdf_path)
    mismatched = sorted(sha for sha in recorded if sha != on_disk)
    if mismatched:
        msg = (
            f"On-disk source PDF {pdf_path} (sha256={on_disk}) does not match the "
            f"resolved run's recorded source_pdf_sha256 ({', '.join(mismatched)}); "
            f"the PDF was replaced after the run rendered against it. Refusing to "
            f"splice images from a PDF the bound run never saw."
        )
        raise RunResolutionError(msg)


def resolve_source_pdf(doc_id: str, *, repo_root: Path | None = None) -> tuple[Path, int]:
    """Resolve (source_pdf_path, page_count) for ``doc_id`` from its config.

    Reads ``configs/documents/{doc_id}.toml`` via ``load_document_config``
    (which honours ``[document].source_pdf`` and resolves it against the
    repo root). If the PDF exists, returns its real page count via
    PyMuPDF. If the PDF is absent, returns ``(path, 0)`` so call-sites can
    skip extraction cleanly instead of silently falling back to ATO.

    Added in S5U-688 to replace the repo-global ``PDF_PATH`` constant that
    caused cross-document image leakage for ``--doc walking_skeleton`` etc.
    """
    from atr_pipeline.config.loader import load_document_config

    cfg = load_document_config(doc_id, repo_root=repo_root)
    pdf_path = cfg.source_pdf_path
    if not pdf_path.exists():
        return pdf_path, 0

    import fitz

    doc = fitz.open(str(pdf_path))
    try:
        page_count = len(doc)
    finally:
        doc.close()
    return pdf_path, page_count


def extract_images(
    doc_id: str,
    doc_public: Path,
    target_dir: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, list[dict]]:
    """Extract images from the document's configured source PDF.

    The source PDF and page range are derived from the document config
    (``configs/documents/{doc_id}.toml``) — never from a repo-global
    constant (S5U-688). Emits ``{}`` when the configured PDF is missing so
    non-ATO exports do not silently inherit ATO imagery.

    ``target_dir`` is the directory the decoded image bytes are written into.
    The exporter passes a *staging* dir here (S5U-1223) so a phase-2 validation
    refusal never leaves the live ``images/`` dir mutated; the staged dir is
    swapped atomically into place alongside the editions. When omitted it
    defaults to the live ``doc_public / "images"`` for backward compatibility.
    The returned ``page_images`` ``src`` URLs are always the published
    ``/documents/{doc_id}/images/{fname}`` path regardless of the on-disk write
    location — only the build-time write target changes.
    """
    pdf_path, page_count = resolve_source_pdf(doc_id, repo_root=repo_root)
    if page_count == 0:
        print(f"  PDF not found at {pdf_path}, skipping image extraction")
        return {}

    from atr_pipeline.services.pdf.image_extractor import extract_page_images

    img_dir = target_dir if target_dir is not None else doc_public / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    page_images: dict[str, list[dict]] = {}
    total = 0
    for pnum in range(1, page_count + 1):
        pid = f"p{pnum:04d}"
        try:
            images = extract_page_images(pdf_path, page_number=pnum, min_width=100, min_height=100)
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
