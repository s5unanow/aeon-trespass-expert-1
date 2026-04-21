"""Source-PDF resolution and per-page image extraction for web export.

Lives outside ``export_to_web.py`` so the main script stays under the
repo's 400-line ceiling (S5U-688).
"""

from __future__ import annotations

from pathlib import Path


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
    doc_id: str, doc_public: Path, *, repo_root: Path | None = None
) -> dict[str, list[dict]]:
    """Extract images from the document's configured source PDF.

    The source PDF and page range are derived from the document config
    (``configs/documents/{doc_id}.toml``) — never from a repo-global
    constant (S5U-688). Emits ``{}`` when the configured PDF is missing so
    non-ATO exports do not silently inherit ATO imagery.
    """
    pdf_path, page_count = resolve_source_pdf(doc_id, repo_root=repo_root)
    if page_count == 0:
        print(f"  PDF not found at {pdf_path}, skipping image extraction")
        return {}

    from atr_pipeline.services.pdf.image_extractor import extract_page_images

    img_dir = doc_public / "images"
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
