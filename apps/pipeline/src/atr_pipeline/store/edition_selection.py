"""Edition-aware artifact selection helpers (S5U-731).

Both the web exporter (``scripts/export_to_web.py``) and the QA stage
(``apps/pipeline/src/atr_pipeline/stages/qa``) load the latest render
artifact for a page from disk. Before this module landed they used two
different policies:

* The exporter used a two-tier edition-aware selection in
  ``_pick_latest``:
    1. Prefer artifacts whose ``document_version == edition``.
    2. Fall back to untagged (``document_version == ""``) only when no
       tagged artifact for *any* edition exists.
* QA used :py:meth:`ArtifactStore.load_latest_json` which selects newest
  by mtime with no edition filtering.

In a mixed EN/RU artifact directory — the common case after a full
pipeline run — that meant QA could build its ``known_page_numbers``
manifest and evaluate rules against a different-edition render than the
one the reader actually publishes.

This module is the single source of truth for the policy. The exporter's
``_pick_latest`` and the QA loaders both consume :func:`pick_latest_for_edition`
(raw paths) or :func:`load_latest_json_for_edition` (via
:class:`ArtifactStore`). Two semantically-equivalent threats motivated
the ``edition_field=`` knob (so future edition-tagged artifact classes
that use a different field name — e.g. ``edition`` — can share the same
algorithm without code duplication):

1. Translation / symbol-resolution / review-pack artifacts use
   ``edition`` rather than ``document_version``.
2. The QA-summary loader in ``scripts/_export_qa.py::_pick_summary_for_edition``
   already implements the same algorithm against the ``edition`` field.

The "Linear must refuse" rules in S5U-731 are upheld by this design:

* The two sites cannot drift because they share the helper (no
  copy-pasted logic).
* Edition tags on render artifacts are still required for tier-1
  selection — the helper falls back to tier-2 (untagged) only when no
  tagged artifact exists, so removing tags would *degrade* selection,
  not enable it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atr_pipeline.store.artifact_store import ArtifactStore, latest_sort_key

DEFAULT_EDITION_FIELD = "document_version"


def _is_filterable_edition(edition: str) -> bool:
    """True iff *edition* identifies a specific edition to filter by.

    Empty string and ``"all"`` mean "no edition signal" — fall back to
    newest-by-mtime selection across the entire candidate set.
    """
    return bool(edition) and edition != "all"


def pick_latest_for_edition(
    files: list[Path],
    edition: str,
    *,
    edition_field: str = DEFAULT_EDITION_FIELD,
) -> dict[str, Any] | None:
    """Two-tier edition-aware selection across raw artifact paths.

    Selection rules when *edition* is filterable (i.e. not ``""`` and not
    ``"all"``):

    1. **Exact match** — newest by mtime among files whose payload's
       ``edition_field`` equals *edition*.
    2. **Untagged fallback** — newest by mtime among files with empty
       ``edition_field``, used only when *no* file has a non-empty tag.
       This preserves backwards compatibility for pre-S5U-402 artifacts
       (which carry ``document_version=""``) while preventing
       cross-edition contamination once any tagged artifact exists for
       a sibling edition.

    When *edition* is ``""`` or ``"all"`` the helper returns the newest
    file by mtime regardless of tag — matching the
    :py:meth:`ArtifactStore.load_latest_json` semantics.

    Returns the parsed JSON dict of the winning artifact, or ``None``
    when no artifact matches.

    S5U-1229 — selection resolves the winning *path* first and parses
    only that one file, instead of parsing (and retaining) every
    candidate. The field-read pass still does a full, fail-loud
    ``json.load`` per candidate (no fragile substring/regex peek — a
    corrupt candidate must surface, not be silently mis-selected), but
    the returned payload is parsed exactly once. mtime ties are broken
    deterministically by the same ``latest_sort_key`` the store uses, so
    the winner is reproducible rather than ``glob``-order dependent.
    """
    if not files:
        return None

    if not _is_filterable_edition(edition):
        # Newest by mtime, no filtering — backwards-compatible with the
        # pre-S5U-731 ``load_latest_json`` behavior.
        return _read_json(max(files, key=latest_sort_key))

    return _select_edition_payload(files, edition, edition_field)


def _select_edition_payload(
    files: list[Path],
    edition: str,
    edition_field: str,
) -> dict[str, Any] | None:
    """Two-tier edition selection over *files*, returning the winner's payload.

    Each candidate is parsed once (a full, fail-loud ``json.load`` — a
    corrupt candidate raises here rather than being silently skipped) and
    classified as exact-match / other-tagged / untagged. Only the winning
    payload per tier is retained; the rest are discarded after their tag is
    read. mtime ties are broken deterministically by ``latest_sort_key``.
    The winner is therefore parsed exactly once and never re-read from disk.
    """
    best_exact: dict[str, Any] | None = None
    best_exact_key: tuple[float, str] | None = None
    best_untagged: dict[str, Any] | None = None
    best_untagged_key: tuple[float, str] | None = None
    has_any_tagged = False

    for path in files:
        data = _read_json(path)
        tag = str(data.get(edition_field, ""))
        key = latest_sort_key(path)

        if tag == edition:
            if best_exact_key is None or key > best_exact_key:
                best_exact = data
                best_exact_key = key
        elif tag != "":
            has_any_tagged = True
        elif best_untagged_key is None or key > best_untagged_key:
            best_untagged = data
            best_untagged_key = key

    if best_exact is not None:
        return best_exact
    if not has_any_tagged:
        return best_untagged
    return None


def load_latest_json_for_edition(
    store: ArtifactStore,
    *,
    document_id: str,
    schema_family: str,
    scope: str,
    entity_id: str,
    edition: str,
    edition_field: str = DEFAULT_EDITION_FIELD,
) -> dict[str, Any] | None:
    """Edition-aware analog of :py:meth:`ArtifactStore.load_latest_json`.

    Resolves the entity directory under the artifact-store root, then
    delegates to :func:`pick_latest_for_edition`. When *edition* is
    ``""`` or ``"all"`` the result is identical to
    :py:meth:`ArtifactStore.load_latest_json` — the helper degrades
    gracefully on edition-agnostic call sites (e.g. the ``atr qa`` CLI
    which has no edition contract).
    """
    entity_dir = store.root / document_id / schema_family / scope / entity_id
    if not entity_dir.exists():
        return None
    files = list(entity_dir.glob("*.json"))
    if not files:
        return None
    return pick_latest_for_edition(files, edition, edition_field=edition_field)


def _read_json(path: Path) -> dict[str, Any]:
    """Read JSON from *path*; propagates :class:`json.JSONDecodeError`.

    Mirrors the fail-fast behavior of the original
    ``scripts/export_to_web.py::_pick_latest`` and
    :py:meth:`ArtifactStore.load_latest_json`: a corrupt artifact in the
    candidate directory is treated as a hard failure rather than
    silently skipped. The QA stage and the exporter both run in CI
    pipelines where a malformed JSON is a regression to surface, not
    paper over.
    """
    with path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data
