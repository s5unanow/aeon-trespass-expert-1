"""Reader-publishability filter for QA's dead-page-ref suppression manifest.

S5U-730: the QA stage's ``known_page_numbers`` set must agree with the
web reader's published page set. The exporter publishes a page when its
render artifact exists AND the page is either in facsimile mode, has at
least one renderable block, OR has at least one source-PDF image that
``scripts/_export_blocks.inject_image_figures`` would inject.

These helpers are shared between ``atr_pipeline.stages.qa.stage.QAStage``
and the CLI ``atr_pipeline.cli.commands.qa`` entrypoint so the two
codepaths cannot drift on what "publishable" means.
"""

from __future__ import annotations

from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.store.edition_selection import load_latest_json_for_edition

# S5U-730 — exporter image-injection rescue threshold (must match the
# values in ``scripts/_export_images.extract_images``: ``min_width=100``,
# ``min_height=100``). Hardcoded here because the QA stage cannot import
# from ``scripts/`` without inverting the dependency direction. If the
# exporter's threshold ever changes, both must move together.
EXPORTER_RESCUE_MIN_WIDTH_PX = 100
EXPORTER_RESCUE_MIN_HEIGHT_PX = 100


def page_images_manifest_present(store: ArtifactStore, document_id: str) -> bool:
    """Return True if the document has at least one ``page_images.v1`` artifact.

    Used by ``filter_publishable_pages`` to detect legacy artifact stores
    that predate S5U-730 (i.e. produced before ``IngestStage.version``
    was bumped to 1.1). On those stores the manifest is absent for the
    whole document; QA falls back to the pre-S5U-730 render-only filter
    for backwards compatibility. Per ``.claude/rules/guards.md`` Rule G1
    this is fail-closed: the fallback is the *narrower* (pre-fix)
    suppression set, never a wider permissive view that would
    re-introduce the FP S5U-730 fixes.
    """
    manifest_root = store.root / document_id / "page_images.v1" / "page"
    return manifest_root.exists() and any(manifest_root.iterdir())


def page_has_rescuable_images(store: ArtifactStore, document_id: str, page_id: str) -> bool:
    """Return True if the page's ``page_images.v1`` manifest carries at
    least one image meeting the exporter's rescue threshold."""
    data = store.load_latest_json(
        document_id=document_id,
        schema_family="page_images.v1",
        scope="page",
        entity_id=page_id,
    )
    if not data:
        return False
    images = data.get("images")
    if not isinstance(images, list):
        return False
    for entry in images:
        if not isinstance(entry, dict):
            continue
        try:
            width = int(entry.get("width_px", 0))
            height = int(entry.get("height_px", 0))
        except (TypeError, ValueError):
            continue
        if width >= EXPORTER_RESCUE_MIN_WIDTH_PX and height >= EXPORTER_RESCUE_MIN_HEIGHT_PX:
            return True
    return False


def filter_publishable_pages(
    store: ArtifactStore, document_id: str, page_ids: list[str], *, edition: str = ""
) -> list[str]:
    """Return the subset of *page_ids* the web exporter will publish.

    Mirrors the filter in ``scripts/export_to_web.py::export_pages``:
    a page is published iff a render artifact exists for it AND the
    page is either in facsimile mode, has at least one renderable
    block, OR has at least one source-PDF image that the exporter's
    ``inject_image_figures`` rescue would inject (S5U-730).

    The image-rescue branch reads the ``page_images.v1`` manifest
    emitted by ``IngestStage`` and applies the exporter's threshold
    (``min_width=100, min_height=100``) so the QA suppression set
    agrees with reader reality without having to load the source
    PDF on every QA invocation.

    Keeps the dead-page-ref suppression manifest aligned with what
    the reader actually sees — a page that EN IR knows about but
    the exporter drops is still dead from the reader's perspective
    and must not be suppressed (Codex REVISE round 2 / S5U-701);
    a page that EN IR has nothing for but which the exporter
    rescues from PDF imagery alone is published and must NOT fire
    DEAD_PAGE_REF (S5U-730).

    S5U-731 — when *edition* is ``"en"`` or ``"ru"`` the render-load
    routes through the shared edition-aware helper so the
    publishability set matches the reader's edition-isolated view
    on mixed EN/RU artifact dirs. Empty / ``"all"`` edition preserves
    the pre-S5U-731 newest-by-mtime semantics for legacy callers.
    """
    publishable: list[str] = []
    manifest_present = page_images_manifest_present(store, document_id)
    for pid in page_ids:
        data = load_latest_json_for_edition(
            store,
            document_id=document_id,
            schema_family="render_page.v1",
            scope="page",
            entity_id=pid,
            edition=edition,
        )
        if not data:
            # No render artifact → exporter skips it entirely (the
            # ``if not jsons: continue`` branch in
            # ``export_to_web.py::export_pages``); it cannot be
            # rescued by image injection because that runs *on* the
            # render data.
            continue
        presentation = data.get("presentation_mode")
        blocks = data.get("blocks") or []
        if presentation == "facsimile" or blocks:
            publishable.append(pid)
            continue
        # Render artifact present but article-mode with zero blocks:
        # the exporter's ``inject_image_figures`` rescue applies. The
        # page is published iff ingest extracted ≥1 image meeting the
        # exporter's ``min_width=100, min_height=100`` threshold
        # (S5U-730).
        if manifest_present and page_has_rescuable_images(store, document_id, pid):
            publishable.append(pid)
    return publishable
