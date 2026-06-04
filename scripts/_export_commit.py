"""Two-phase, fail-closed commit for the `make export` path (S5U-890).

S5U-869 made the export *ref-bound* (one run per edition, no mtime splice), but
the writer still mutated the live web bundle edition-by-edition **before** it had
proven the whole bundle exportable. Several late-failure paths therefore left a
partial or cross-edition bundle on disk after a non-zero exit:

* a missing glossary ref file refused *after* rasters/pages/manifest were
  written,
* post-write ``run_export_validation`` failure left the just-written bundle
  live,
* in ``--edition all`` the EN bundle was fully written before RU could refuse —
  a cross-edition splice (EN=run B, RU=run A), the exact integrity property
  S5U-869 set out to guarantee.

This module turns the per-edition build into a temp-dir staging build plus a
crash-safe atomic swap, and only swaps **after every edition** has been built
and validated in staging. A late RU-side failure therefore cannot leave a
written EN bundle: nothing live is mutated until the whole bundle is proven.

Fail-closed contract (`.claude/rules/guards.md` Rule G1): every degenerate input
(missing glossary/raster/page-ref/QA-summary file, post-write validation
failure, EN-resolves-but-RU-does-not) refuses *before any live mutation*. A swap
failure mid-``--edition all`` rolls back already-swapped editions from their
backups so no half-swapped cross-edition state persists.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Prefix for the sibling-of-``<edition>`` staging dirs. They are direct children
# of ``doc_public`` so ``_export_validation.validate_asset_existence`` — which
# derives ``doc_public = data_dir.parent.parent`` — still resolves figure src
# paths against the live shared ``images/`` dir. A different layout would break
# that arithmetic.
_STAGE_PREFIX = ".stage-"
_BACKUP_PREFIX = ".backup-"


@dataclass(frozen=True)
class StagedEdition:
    """One edition built into a staging dir, ready for the atomic swap.

    ``validation_ok`` is the post-build ``run_export_validation`` verdict against
    the *staged* edition dir — a ``False`` here aborts the whole commit before
    any swap (the live bundle is never touched).
    """

    edition: str
    staging_dir: Path
    live_dir: Path
    validation_ok: bool


def _swap_dir(staged: Path, live: Path, backup: Path) -> None:
    """Atomically replace *live* with *staged*, parking the old *live* at *backup*.

    ``os.replace`` cannot replace a non-empty directory, so the live dir is first
    moved aside to *backup* (crash-safe: a mid-swap crash leaves the prior good
    bundle recoverable at *backup*), then the staged dir is moved into place.
    The caller deletes *backup* only after every edition swapped successfully.
    """
    if live.exists():
        os.replace(live, backup)
    os.replace(staged, live)


def _restore_dir(live: Path, backup: Path) -> None:
    """Roll a single edition back: discard the swapped-in dir, restore the backup."""
    if backup.exists():
        if live.exists():
            shutil.rmtree(live)
        os.replace(backup, live)


def _cleanup_path(path: Path) -> None:
    """Best-effort removal of a leftover staging/backup dir (idempotent)."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _staging_and_backup_dirs(doc_public: Path, editions: list[str], pid: int) -> list[Path]:
    """All staging + backup dirs this process owns for the given editions + rasters."""
    dirs: list[Path] = []
    for edition in editions:
        dirs.append(doc_public / f"{_STAGE_PREFIX}{edition}-{pid}")
        dirs.append(doc_public / f"{_BACKUP_PREFIX}{edition}-{pid}")
    dirs.append(doc_public / f"{_STAGE_PREFIX}rasters-{pid}")
    dirs.append(doc_public / f"{_BACKUP_PREFIX}rasters-{pid}")
    return dirs


def reset_staging(
    doc_public: Path, editions: list[str], pid: int, staged_rasters_dir: Path
) -> None:
    """Remove any leftover staging/backup dirs before a build (idempotent).

    Guards against a crashed prior export of the *same* pid leaving partial
    staging state. ``staged_rasters_dir`` is recreated empty so the build copies
    every edition's rasters into one dir for a single doc-scoped swap.
    """
    for path in _staging_and_backup_dirs(doc_public, editions, pid):
        _cleanup_path(path)
    staged_rasters_dir.mkdir(parents=True, exist_ok=True)


def cleanup_staging(
    doc_public: Path, editions: list[str], pid: int, staged_rasters_dir: Path
) -> None:
    """Remove all of this process's staging/backup dirs after a refusal.

    Called on every fail-closed exit path so a refused export leaves no
    ``.stage-*`` / ``.backup-*`` litter next to the (untouched) live bundle.
    """
    for path in _staging_and_backup_dirs(doc_public, editions, pid):
        _cleanup_path(path)
    _cleanup_path(staged_rasters_dir)


def stage_paths(doc_public: Path, edition: str, pid: int) -> tuple[Path, Path, Path]:
    """Return (staging_dir, live_dir, backup_dir) for an edition build.

    All three are direct children of ``doc_public`` and therefore on the same
    filesystem, so ``os.replace`` between them is atomic. ``pid`` namespaces the
    staging/backup dirs to the running process so concurrent exports of
    different docs (or a crashed prior run's leftovers) cannot collide.
    """
    staging_dir = doc_public / f"{_STAGE_PREFIX}{edition}-{pid}"
    live_dir = doc_public / edition
    backup_dir = doc_public / f"{_BACKUP_PREFIX}{edition}-{pid}"
    return staging_dir, live_dir, backup_dir


def build_edition_into_staging(
    doc_public: Path,
    edition: str,
    pid: int,
    build: Callable[[Path], bool],
) -> StagedEdition:
    """Build one edition into a fresh staging dir; return the staged result.

    ``build(staging_dir)`` runs every existing transform (rasters → pages →
    glossary → qa → validation) against ``staging_dir`` instead of the live
    edition dir, and returns the ``run_export_validation`` verdict. Any
    ``RunResolutionError`` raised by ``build`` (missing glossary/raster file)
    propagates out *before* any swap — the live bundle is never touched.

    The staging dir is removed and recreated empty first, so a wholesale
    directory swap inherently discards every stale companion the prior live
    bundle held (the S5U-892 invariant holds for free under staging).
    """
    staging_dir, live_dir, _ = stage_paths(doc_public, edition, pid)
    _cleanup_path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    validation_ok = build(staging_dir)
    return StagedEdition(
        edition=edition,
        staging_dir=staging_dir,
        live_dir=live_dir,
        validation_ok=validation_ok,
    )


def _swap_rasters(
    doc_public: Path, staged_rasters: Path | None, pid: int, swapped: list[tuple[Path, Path]]
) -> None:
    """Swap the doc-scoped ``rasters/`` dir from staging into place, if any.

    Only swaps when the staged dir actually holds raster PNGs. A run with no
    facsimile pages stages an empty rasters dir; swapping that over the live
    ``rasters/`` would delete a prior run's rasters that the current bundle does
    not reference — so we leave the live dir untouched in that case (matching the
    pre-S5U-890 behavior where a no-facsimile export never wrote rasters).
    """
    if staged_rasters is None or not staged_rasters.is_dir() or not any(staged_rasters.iterdir()):
        return
    live_rasters = doc_public / "rasters"
    backup_rasters = doc_public / f"{_BACKUP_PREFIX}rasters-{pid}"
    _swap_dir(staged_rasters, live_rasters, backup_rasters)
    swapped.append((live_rasters, backup_rasters))


def commit_staged(
    staged_editions: list[StagedEdition],
    *,
    doc_public: Path,
    pid: int,
    staged_rasters: Path | None,
) -> None:
    """Atomically swap every staged edition (+ rasters) into the live bundle.

    All-or-nothing: if any edition failed validation in staging, nothing is
    swapped and :class:`ExportCommitError` is raised (the live bundle stays
    byte-identical to before). On a swap-time ``OSError`` after one or more
    editions have already swapped, every swapped dir is rolled back from its
    backup before re-raising, so no half-swapped cross-edition state persists.
    """
    failed = [s.edition for s in staged_editions if not s.validation_ok]
    if failed:
        for s in staged_editions:
            _cleanup_path(s.staging_dir)
        if staged_rasters is not None:
            _cleanup_path(staged_rasters)
        raise ExportCommitError(
            f"Export validation FAILED for edition(s) {', '.join(failed)}; "
            f"refusing to publish — live bundle left unchanged."
        )

    swapped: list[tuple[Path, Path]] = []  # (live_dir, backup_dir) for rollback
    try:
        _swap_rasters(doc_public, staged_rasters, pid, swapped)
        for s in staged_editions:
            _, _, backup_dir = stage_paths(doc_public, s.edition, pid)
            _swap_dir(s.staging_dir, s.live_dir, backup_dir)
            swapped.append((s.live_dir, backup_dir))
    except OSError as exc:
        logger.error("Export swap failed (%s); rolling back %d swapped dir(s)", exc, len(swapped))
        for live_dir, backup_dir in reversed(swapped):
            try:
                _restore_dir(live_dir, backup_dir)
            except OSError as restore_exc:  # pragma: no cover - manual-recovery path
                logger.error(
                    "Rollback of %s from %s FAILED: %s — backup retained for manual recovery",
                    live_dir,
                    backup_dir,
                    restore_exc,
                )
        raise
    # Every swap succeeded — discard the parked backups and any staging dir that
    # was not swapped (an empty rasters staging dir for a no-facsimile export).
    for _, backup_dir in swapped:
        _cleanup_path(backup_dir)
    if staged_rasters is not None:
        _cleanup_path(staged_rasters)


class ExportCommitError(Exception):
    """A staged export could not be committed — fail closed, live bundle intact."""
