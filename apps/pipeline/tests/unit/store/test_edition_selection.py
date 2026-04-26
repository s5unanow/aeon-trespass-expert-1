"""Tests for ``atr_pipeline.store.edition_selection`` (S5U-731).

The helpers in ``edition_selection`` are the single source of truth for
the two-tier ``document_version`` policy shared between the web
exporter (``scripts/export_to_web.py::_pick_latest``) and the QA stage
(``apps/pipeline/src/atr_pipeline/stages/qa/``). Both sites previously
implemented divergent selection: the exporter was edition-aware, QA
was newest-by-mtime. On mixed EN/RU artifact dirs (the common case
after a full pipeline run) QA loaded the wrong-edition render.

The §4d adversarial matrix from ``tmp/plan-s5u-731.md`` is exercised
below.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.store.edition_selection import (
    load_latest_json_for_edition,
    pick_latest_for_edition,
)


def _write_render(path: Path, *, document_version: str, body: str = "") -> Path:
    """Create a render-shaped JSON file at *path*. Returns the path."""
    payload = {
        "schema_version": "1.0",
        "document_version": document_version,
        "page": {"page_id": "p0001", "title": "T"},
        "blocks": [
            {"kind": "paragraph", "id": "p0001.b1", "children": [{"kind": "text", "text": body}]}
        ],
    }
    path.write_text(json.dumps(payload))
    return path


class TestPickLatestForEdition:
    """Direct exercise of the raw-paths helper."""

    def test_mixed_run_picks_en_for_en_edition(self, tmp_path: Path) -> None:
        """RED-BEFORE: with the legacy ``load_latest_json`` selection the
        RU artifact (newer mtime) wins regardless of ``ctx.edition``.
        With the edition-aware helper, EN is picked."""
        en_path = _write_render(tmp_path / "en.json", document_version="en", body="Example")
        os.utime(en_path, (1_000_000, 1_000_000))
        ru_path = _write_render(tmp_path / "ru.json", document_version="ru", body="Пример")
        os.utime(ru_path, (2_000_000, 2_000_000))

        result = pick_latest_for_edition([en_path, ru_path], "en")

        assert result is not None
        assert result["document_version"] == "en"
        assert result["blocks"][0]["children"][0]["text"] == "Example"

    def test_mixed_run_picks_ru_for_ru_edition(self, tmp_path: Path) -> None:
        """Mirror of the above: requesting RU when EN is newer must
        still return the RU payload."""
        en_path = _write_render(tmp_path / "en.json", document_version="en", body="Example")
        os.utime(en_path, (3_000_000, 3_000_000))
        ru_path = _write_render(tmp_path / "ru.json", document_version="ru", body="Пример")
        os.utime(ru_path, (1_000_000, 1_000_000))

        result = pick_latest_for_edition([en_path, ru_path], "ru")

        assert result is not None
        assert result["document_version"] == "ru"

    def test_homogeneous_run_unchanged(self, tmp_path: Path) -> None:
        """§4d (a): edition-homogeneous runs (all artifacts same edition)
        return the newest among them — no observable change vs pre-fix."""
        a = _write_render(tmp_path / "a.json", document_version="en", body="A")
        os.utime(a, (1_000_000, 1_000_000))
        b = _write_render(tmp_path / "b.json", document_version="en", body="B")
        os.utime(b, (2_000_000, 2_000_000))

        result = pick_latest_for_edition([a, b], "en")

        assert result is not None
        assert result["blocks"][0]["children"][0]["text"] == "B"

    def test_untagged_legacy_fallback(self, tmp_path: Path) -> None:
        """§4d (d): untagged-only run (legacy data pre-S5U-402) → tier-2
        fallback returns the newest untagged artifact."""
        a = _write_render(tmp_path / "a.json", document_version="", body="L1")
        os.utime(a, (1_000_000, 1_000_000))
        b = _write_render(tmp_path / "b.json", document_version="", body="L2")
        os.utime(b, (2_000_000, 2_000_000))

        result = pick_latest_for_edition([a, b], "en")

        assert result is not None
        assert result["blocks"][0]["children"][0]["text"] == "L2"

    def test_untagged_suppressed_when_other_tagged_exists(self, tmp_path: Path) -> None:
        """The original S5U-437 contract: untagged fallback is suppressed
        once *any* tagged artifact for a sibling edition exists. EN
        request with only RU-tagged + untagged returns ``None`` — the
        page has edition-specific content but not for the requested
        edition."""
        untagged = _write_render(tmp_path / "u.json", document_version="", body="?")
        os.utime(untagged, (1_000_000, 1_000_000))
        ru_tagged = _write_render(tmp_path / "ru.json", document_version="ru", body="Пример")
        os.utime(ru_tagged, (2_000_000, 2_000_000))

        result = pick_latest_for_edition([untagged, ru_tagged], "en")

        assert result is None

    def test_empty_edition_returns_newest(self, tmp_path: Path) -> None:
        """§4d (g): empty / "all" edition preserves newest-by-mtime."""
        a = _write_render(tmp_path / "a.json", document_version="en", body="A")
        os.utime(a, (1_000_000, 1_000_000))
        b = _write_render(tmp_path / "b.json", document_version="ru", body="B")
        os.utime(b, (2_000_000, 2_000_000))

        for edition in ("", "all"):
            result = pick_latest_for_edition([a, b], edition)
            assert result is not None
            assert result["blocks"][0]["children"][0]["text"] == "B"

    def test_no_files_returns_none(self, tmp_path: Path) -> None:
        """§4d (h)."""
        assert pick_latest_for_edition([], "en") is None

    def test_no_match_for_edition_returns_none(self, tmp_path: Path) -> None:
        """When only RU-tagged artifacts exist and EN is requested, return
        ``None`` (forced by the tier-2 suppression)."""
        ru_only = _write_render(tmp_path / "ru.json", document_version="ru")
        os.utime(ru_only, (1_000_000, 1_000_000))

        assert pick_latest_for_edition([ru_only], "en") is None

    def test_custom_edition_field_for_future_artifact_classes(self, tmp_path: Path) -> None:
        """§4d (f): future artifact classes (translation/symbol-resolution/
        review-pack) tag with ``edition`` rather than ``document_version``.
        The same algorithm reuses cleanly through ``edition_field=``."""
        a = tmp_path / "a.json"
        a.write_text(json.dumps({"edition": "en", "data": "EN"}))
        os.utime(a, (1_000_000, 1_000_000))
        b = tmp_path / "b.json"
        b.write_text(json.dumps({"edition": "ru", "data": "RU"}))
        os.utime(b, (2_000_000, 2_000_000))

        result = pick_latest_for_edition([a, b], "en", edition_field="edition")

        assert result is not None
        assert result["data"] == "EN"

    def test_malformed_json_propagates(self, tmp_path: Path) -> None:
        """§4d (i): a corrupt artifact must surface, not be silently
        skipped — matches the fail-fast policy of the original
        ``_pick_latest`` and ``ArtifactStore.load_latest_json``."""
        bad = tmp_path / "bad.json"
        bad.write_text("{ not valid")
        os.utime(bad, (2_000_000, 2_000_000))

        with pytest.raises(json.JSONDecodeError):
            pick_latest_for_edition([bad], "en")


class TestLoadLatestJsonForEdition:
    """Exercise the ArtifactStore-backed entrypoint used by QAStage."""

    def test_qa_loader_picks_correct_edition_on_mixed_dir(self, tmp_path: Path) -> None:
        """RED-BEFORE: the same dir loaded via ``store.load_latest_json``
        returns the newest by mtime (RU). The edition-aware helper picks
        the EN payload when the QA stage runs with ``edition="en"``."""
        store = ArtifactStore(tmp_path)
        entity_dir = tmp_path / "doc1" / "render_page.v1" / "page" / "p0001"
        entity_dir.mkdir(parents=True)

        en_file = _write_render(entity_dir / "hash_en.json", document_version="en", body="EN")
        os.utime(en_file, (1_000_000, 1_000_000))
        ru_file = _write_render(entity_dir / "hash_ru.json", document_version="ru", body="RU")
        os.utime(ru_file, (2_000_000, 2_000_000))

        # Newest-by-mtime would have returned RU…
        legacy = store.load_latest_json(
            document_id="doc1",
            schema_family="render_page.v1",
            scope="page",
            entity_id="p0001",
        )
        assert legacy is not None
        assert legacy["document_version"] == "ru"

        # …but the edition-aware helper returns EN.
        edition_aware = load_latest_json_for_edition(
            store,
            document_id="doc1",
            schema_family="render_page.v1",
            scope="page",
            entity_id="p0001",
            edition="en",
        )
        assert edition_aware is not None
        assert edition_aware["document_version"] == "en"
        assert edition_aware["blocks"][0]["children"][0]["text"] == "EN"

    def test_missing_entity_dir_returns_none(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path)
        result = load_latest_json_for_edition(
            store,
            document_id="doc1",
            schema_family="render_page.v1",
            scope="page",
            entity_id="p0099",
            edition="en",
        )
        assert result is None

    def test_empty_entity_dir_returns_none(self, tmp_path: Path) -> None:
        store = ArtifactStore(tmp_path)
        entity_dir = tmp_path / "doc1" / "render_page.v1" / "page" / "p0001"
        entity_dir.mkdir(parents=True)
        result = load_latest_json_for_edition(
            store,
            document_id="doc1",
            schema_family="render_page.v1",
            scope="page",
            entity_id="p0001",
            edition="en",
        )
        assert result is None

    def test_empty_edition_matches_load_latest_json_semantics(self, tmp_path: Path) -> None:
        """When the call site has no edition contract (e.g. CLI ``atr qa``)
        the helper behaves like the original ``load_latest_json``."""
        store = ArtifactStore(tmp_path)
        entity_dir = tmp_path / "doc1" / "render_page.v1" / "page" / "p0001"
        entity_dir.mkdir(parents=True)

        a = _write_render(entity_dir / "hash_a.json", document_version="en", body="A")
        os.utime(a, (1_000_000, 1_000_000))
        b = _write_render(entity_dir / "hash_b.json", document_version="ru", body="B")
        os.utime(b, (2_000_000, 2_000_000))

        legacy = store.load_latest_json(
            document_id="doc1",
            schema_family="render_page.v1",
            scope="page",
            entity_id="p0001",
        )
        edition_aware = load_latest_json_for_edition(
            store,
            document_id="doc1",
            schema_family="render_page.v1",
            scope="page",
            entity_id="p0001",
            edition="",
        )
        assert legacy == edition_aware


class TestQAStageVersionBumpPresent:
    """Cache-discipline guard for S5U-731 (S5U-662 worked-example shape).

    The QA stage's render selection observably changes on mixed EN/RU
    artifact dirs (different render → potentially different QA records).
    Per ``.claude/rules/pipeline.md`` § "Stage-output cache invalidation"
    the stage version must be bumped in the same PR so cached events
    from the prior version don't silently short-circuit ``run()`` and
    leave QA evaluating the wrong-edition render.
    """

    def test_qa_stage_version_post_s5u_731(self) -> None:
        """RED-BEFORE: prior to S5U-731 ``QAStage.version`` was ``"1.8"``;
        if a future refactor reverts to the pre-fix selection without
        bumping the version, cached events from the buggy run would
        silently survive. This test pins the version forward (the
        implementation must update it on each behavior-changing PR)."""
        from atr_pipeline.stages.qa.stage import QAStage

        version = QAStage().version
        # Must be a strict version increase past 1.8 — implementations
        # past S5U-731 will be 1.9 or higher.
        major, minor = version.split(".", 1)
        assert int(major) >= 1
        assert (int(major), int(minor)) >= (1, 9), (
            f"QAStage.version must be ≥ 1.9 after S5U-731 to invalidate "
            f"caches that loaded wrong-edition renders, got {version!r}"
        )
