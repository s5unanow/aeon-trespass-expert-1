#!/usr/bin/env python3
"""Export pipeline artifacts to apps/web/public/documents/{doc_id}/{edition}/."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
REPO = _SCRIPTS_DIR.parent
sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
sys.path.insert(0, str(_SCRIPTS_DIR))

from _export_blocks import export_facsimile_rasters  # noqa: E402
from _export_commit import (  # noqa: E402
    ExportCommitError,
    StagedEdition,
    build_edition_into_staging,
    cleanup_staging,
    commit_staged,
    reset_staging,
)
from _export_images import extract_images, resolve_source_pdf  # noqa: E402
from _export_pages import export_glossary, export_pages  # noqa: E402
from _export_qa import export_qa  # noqa: E402
from _export_qa_gate import (  # noqa: E402
    draft_banner,
    enforce_export_qa_gate,
    stamp_draft_provenance,
)
from _export_run import (  # noqa: E402
    ResolvedRun,
    RunResolutionError,
    load_run_pages,
    resolve_glossary_path,
    resolve_qa_summary_path,
    resolve_run,
)
from _export_validation import run_export_validation  # noqa: E402

from atr_pipeline.config import load_document_config  # noqa: E402
from atr_pipeline.stages.publish.qa_gate import QAGateError, QAGateResult  # noqa: E402

logger = logging.getLogger(__name__)

# Re-exports for S5U-688 regression tests and downstream callers that want to
# import the helpers from the main entry script.
__all__ = ["extract_images", "resolve_source_pdf"]

ARTIFACT_ROOT = REPO / "artifacts"
REGISTRY_PATH = REPO / "var" / "registry.db"


def _load_facsimile_override_pids(doc_id: str) -> list[str]:
    """Load the allowlist of page IDs explicitly marked ``presentation_mode = "facsimile"``.

    Consumed by the S5U-699 publish-time consistency guard in
    ``_export_validation.validate_presentation_mode_payload_consistency``.
    A page appearing in this list is intentionally image-dominant even if
    its blocks payload is substantial (e.g. p0006/p0007 — card-component
    overview pages with dense caption fragments that are meaningful only
    alongside the raster). Pages *not* in this list whose payload still
    advertises facsimile mode while carrying many structured blocks are
    rejected at publish time.

    The allowlist is derived from the **same merged/validated
    ``DocumentBuildConfig``** the render stage consumes (base.toml + env
    overlay + document TOML, validated by pydantic) so the export gate
    cannot drift from the pipeline's classification contract. See the
    S5U-699 Codex review for the contract-split regression this guards
    against.

    Returns a sorted list for deterministic logging.
    """
    config = load_document_config(doc_id)
    return sorted(
        pid
        for pid, override in config.render.page_overrides.items()
        if override.presentation_mode == "facsimile"
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export pipeline artifacts to web viewer")
    parser.add_argument("--doc", default="ato_core_v1_1", help="Document ID")
    parser.add_argument("--edition", choices=["en", "ru", "all"], default="all", help="Edition")
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Pin export to a specific complete run (default: latest complete run "
            "for the document/edition). Refuses if the run is missing or unfinished."
        ),
    )
    parser.add_argument(
        "--review-only",
        dest="review_only",
        action="store_true",
        default=False,
        help=(
            "Escape hatch for the blocking-QA export gate: export a clearly-marked "
            "DRAFT bundle over blocking QA findings (for human review) instead of "
            "refusing. Default is to refuse on blocking QA. Must be passed "
            "explicitly on the command line — there is no env-var toggle "
            "(guards.md G1: an env-only override that flips the default is a "
            "gate bypass)."
        ),
    )
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


@dataclass(frozen=True)
class ResolvedEdition:
    """Phase-1 result for one edition: a single run with every bound ref proven.

    Built by :func:`_resolve_edition` *before any write*. Resolving every ref
    (pages, glossary, QA summary) here is what makes the export fail-closed
    (S5U-890): a missing glossary/page/QA file refuses up front, and resolving
    *all* requested editions before building any of them prevents the EN-before-RU
    cross-edition split.
    """

    edition: str
    resolved: ResolvedRun
    gate_result: QAGateResult
    render_pages: dict[str, dict]
    glossary_path: Path | None
    qa_summary_path: Path | None


def _resolve_edition(
    doc_id: str,
    edition: str,
    run_id: str | None,
    *,
    review_only: bool,
) -> ResolvedEdition:
    """Phase 1: resolve a run and prove every bound artifact exists — no writes.

    Ref-binds the edition to a single complete run (S5U-869), runs the
    blocking-QA gate (S5U-870), and eagerly resolves the page / glossary / QA
    refs so a missing file refuses here (S5U-890) instead of after the bundle is
    partially written. Raises ``RunResolutionError`` / ``QAGateError`` on any
    degenerate input (guards.md Rule G1).
    """
    resolved = resolve_run(
        REGISTRY_PATH,
        doc_id,
        artifact_root=ARTIFACT_ROOT,
        run_id=run_id,
        edition=edition,
    )
    gate_result = enforce_export_qa_gate(
        doc_id,
        edition,
        resolved,
        artifact_root=ARTIFACT_ROOT,
        review_only=review_only,
    )
    render_pages = load_run_pages(resolved, ARTIFACT_ROOT)
    # Pull glossary + QA-summary ref resolution into the pre-write gate (S5U-890):
    # both must prove the referenced file exists before any edition is built.
    glossary_path = resolve_glossary_path(resolved, ARTIFACT_ROOT)
    qa_summary_path = resolve_qa_summary_path(resolved, ARTIFACT_ROOT)
    return ResolvedEdition(
        edition=edition,
        resolved=resolved,
        gate_result=gate_result,
        render_pages=render_pages,
        glossary_path=glossary_path,
        qa_summary_path=qa_summary_path,
    )


def _build_edition(
    doc_id: str,
    re_edition: ResolvedEdition,
    staging_dir: Path,
    staged_rasters_dir: Path,
    page_images: dict[str, list[dict]],
    facsimile_override_pids: list[str],
) -> bool:
    """Phase 2: build one resolved edition into ``staging_dir``. Returns validation OK.

    Writes rasters into ``staged_rasters_dir`` and pages/glossary/QA into
    ``staging_dir`` (a direct child of ``doc_public``), then runs
    ``run_export_validation`` against the staged dir. Nothing live is touched —
    the caller swaps staging into place only after every edition validates.
    """
    edition, resolved = re_edition.edition, re_edition.resolved
    staged_doc_public = doc_public_for(staging_dir)
    print(f"Staging {edition.upper()} render pages from run {resolved.run_id}...")
    if re_edition.gate_result.is_draft:
        print(draft_banner(edition, re_edition.gate_result))
    facsimile_pids = [
        pid
        for pid, data in re_edition.render_pages.items()
        if data.get("presentation_mode") == "facsimile"
    ]
    if facsimile_pids:
        print(f"  Staging rasters for {len(facsimile_pids)} facsimile pages...")
        # Run-bound (S5U-891): rasters come from resolved.raster_refs, not a global
        # scan. A missing raster ref raises here — still pre-swap (S5U-890).
        export_facsimile_rasters(
            staged_doc_public,
            ARTIFACT_ROOT,
            sorted(facsimile_pids),
            resolved.raster_refs,
            rasters_dir=staged_rasters_dir,
        )

    provenance = stamp_draft_provenance(resolved.provenance(), re_edition.gate_result)
    export_pages(
        doc_id,
        edition,
        re_edition.render_pages,
        staged_doc_public,
        page_images,
        provenance,
        edition_dir=staging_dir,
    )
    export_glossary(
        doc_id, edition, re_edition.glossary_path, staged_doc_public, edition_dir=staging_dir
    )
    export_qa(
        ARTIFACT_ROOT,
        doc_id,
        edition,
        staged_doc_public,
        summary_path=re_edition.qa_summary_path,
        ref_bound=True,
        edition_dir=staging_dir,
    )

    manifest = json.loads((staging_dir / "manifest.json").read_text())
    return run_export_validation(staging_dir, manifest["pages"], facsimile_override_pids)


def doc_public_for(staging_dir: Path) -> Path:
    """Parent ``doc_public`` of a staging/edition dir.

    ``validate_asset_existence`` derives ``doc_public = data_dir.parent.parent``
    and resolves ``/documents/...`` figure src paths against the live shared
    ``images/`` dir under it; the staging dir is a direct child of ``doc_public``
    so this parent is the same live ``doc_public`` the assets live under.
    """
    return staging_dir.parent


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    doc_id: str = args.doc
    run_id: str | None = args.run_id
    # review_only is honored ONLY from the explicit argparse flag. There is no
    # env-var read here — an ambient toggle must NOT flip the gate's default
    # (guards.md G1; the issue's "must refuse" env-var-bypass row).
    review_only: bool = args.review_only
    editions = ["en", "ru"] if args.edition == "all" else [args.edition]

    documents_root = REPO / "apps" / "web" / "public" / "documents"
    doc_public = documents_root / doc_id

    print("Extracting images from PDF...")
    page_images = extract_images(doc_id, doc_public, repo_root=REPO)

    facsimile_override_pids = _load_facsimile_override_pids(doc_id)
    if facsimile_override_pids:
        print(f"Config-allowlisted facsimile pages: {', '.join(facsimile_override_pids)}")

    pid = os.getpid()
    staged_rasters_dir = doc_public / f".stage-rasters-{pid}"
    try:
        # Phase 1 — resolve + validate ALL editions before any write (S5U-890).
        resolved_editions = [
            _resolve_edition(doc_id, edition, run_id, review_only=review_only)
            for edition in editions
        ]
        # Phase 2 — build each edition into its own staging dir (no live mutation).
        reset_staging(doc_public, editions, pid, staged_rasters_dir)
        staged: list[StagedEdition] = []
        for resolved_edition in resolved_editions:

            def _build(target: Path, re_edition: ResolvedEdition = resolved_edition) -> bool:
                return _build_edition(
                    doc_id,
                    re_edition,
                    target,
                    staged_rasters_dir,
                    page_images,
                    facsimile_override_pids,
                )

            staged.append(
                build_edition_into_staging(doc_public, resolved_edition.edition, pid, _build)
            )
        # Phase 3 — atomically swap every staged edition (+ rasters) into place.
        commit_staged(
            staged,
            doc_public=doc_public,
            pid=pid,
            staged_rasters=staged_rasters_dir if staged_rasters_dir.is_dir() else None,
        )
    except RunResolutionError as exc:
        cleanup_staging(doc_public, editions, pid, staged_rasters_dir)
        print(f"Export refused: {exc}")
        sys.exit(1)
    except QAGateError as exc:
        cleanup_staging(doc_public, editions, pid, staged_rasters_dir)
        print(f"Export refused: {exc}")
        sys.exit(1)
    except ExportCommitError as exc:
        cleanup_staging(doc_public, editions, pid, staged_rasters_dir)
        print(str(exc))
        sys.exit(1)

    # Reaching here means every edition built, validated, and swapped atomically
    # (commit_staged raises ExportCommitError on any staged-validation failure,
    # caught above with the live bundle left untouched).
    write_document_index(documents_root)
    print("Done.")


if __name__ == "__main__":
    main()
