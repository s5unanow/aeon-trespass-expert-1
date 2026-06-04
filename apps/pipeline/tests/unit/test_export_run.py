"""Tests for scripts/_export_run.py — ref-bound run resolution (S5U-869).

Covers the fail-closed contract (guards.md Rule G1): every degenerate input —
missing/unreadable/empty registry, non-existent or unfinished run, missing
required artifact — must raise ``RunResolutionError`` rather than silently
mtime-falling-back to a different run's artifact. Also covers the issue's
success criteria: cross-run isolation (a two-run repo cannot splice) and a
byte-identical re-export from the same run.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ._export_run_fixtures import NO_RENDER, add_run, init_registry, write_render_result

REPO = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO / "scripts"
RUN_MODULE_PATH = SCRIPTS_DIR / "_export_run.py"


@pytest.fixture()
def run_module() -> Iterator[ModuleType]:
    """Import _export_run.py as a module, cleaning up sys.modules after."""
    sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("_export_run", RUN_MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_run"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_run", None)


@pytest.fixture()
def repo(tmp_path: Path) -> tuple[Path, Path]:
    """Return (registry_path, artifact_root)."""
    return tmp_path / "registry.db", tmp_path / "artifacts"


class TestResolveRunHappyPath:
    def test_resolves_latest_complete_run_and_refs(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        ref = "doc1/render/document/doc1/aaaa.json"
        add_run(
            conn,
            run_id="run_a",
            started_at="2026-01-01T00:00:00",
            render_ref=ref,
            qa_summary_ref="doc1/qa/document/doc1/qa.json",
        )
        conn.close()
        write_render_result(
            artifact_root,
            ref,
            {
                "page_refs": {"p0001": "doc1/render_page.v1/page/p0001/x.json"},
                "image_refs": {"p0001.img0000": "doc1/image/page/p0001.img0000/y.png"},
                "glossary_ref": "doc1/glossary_payload.v1/document/doc1/g.json",
            },
        )

        resolved = run_module.resolve_run(
            registry_path, "doc1", artifact_root=artifact_root, edition="en"
        )

        assert resolved.run_id == "run_a"
        assert resolved.git_commit == "abc123def456"
        assert resolved.edition == "en"
        assert resolved.page_refs == {"p0001": "doc1/render_page.v1/page/p0001/x.json"}
        assert resolved.glossary_ref == "doc1/glossary_payload.v1/document/doc1/g.json"
        assert resolved.qa_summary_ref == "doc1/qa/document/doc1/qa.json"
        assert resolved.provenance()["run_id"] == "run_a"
        assert resolved.provenance()["source_pdf_sha256"] == "pdfsha"

    def test_explicit_run_id_overrides_latest(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        """--run-id pins the named run, not the latest by start time."""
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        ref_old = "doc1/render/document/doc1/old.json"
        ref_new = "doc1/render/document/doc1/new.json"
        add_run(conn, run_id="run_old", started_at="2026-01-01T00:00:00", render_ref=ref_old)
        add_run(conn, run_id="run_new", started_at="2026-02-01T00:00:00", render_ref=ref_new)
        conn.close()
        write_render_result(artifact_root, ref_old, {"page_refs": {"p0001": "old/x.json"}})
        write_render_result(artifact_root, ref_new, {"page_refs": {"p0001": "new/x.json"}})

        resolved = run_module.resolve_run(
            registry_path, "doc1", artifact_root=artifact_root, run_id="run_old"
        )
        assert resolved.run_id == "run_old"
        assert resolved.page_refs == {"p0001": "old/x.json"}

    def test_all_edition_run_satisfies_en_request(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        ref = "doc1/render/document/doc1/all.json"
        add_run(
            conn, run_id="run_all", started_at="2026-01-01T00:00:00", edition="all", render_ref=ref
        )
        conn.close()
        write_render_result(artifact_root, ref, {"page_refs": {"p0001": "x.json"}})

        resolved = run_module.resolve_run(
            registry_path, "doc1", artifact_root=artifact_root, edition="en"
        )
        assert resolved.run_id == "run_all"


class TestResolveRunFailClosed:
    """Each G1 degenerate input must raise RunResolutionError (fail closed)."""

    def test_missing_registry_db_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo  # registry.db never created
        with pytest.raises(run_module.RunResolutionError, match="not found"):
            run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)

    def test_unreadable_registry_db_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo
        registry_path.write_bytes(b"this is not a sqlite database at all")
        with pytest.raises(run_module.RunResolutionError, match="unreadable or corrupt"):
            run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)

    def test_empty_registry_refuses(self, repo: tuple[Path, Path], run_module: ModuleType) -> None:
        registry_path, artifact_root = repo
        init_registry(registry_path).close()  # schema present, zero runs
        with pytest.raises(run_module.RunResolutionError, match="No complete runs"):
            run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)

    def test_nonexistent_run_id_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        add_run(
            conn,
            run_id="run_a",
            started_at="2026-01-01T00:00:00",
            render_ref="doc1/render/document/doc1/a.json",
        )
        conn.close()
        with pytest.raises(run_module.RunResolutionError, match="not found"):
            run_module.resolve_run(
                registry_path, "doc1", artifact_root=artifact_root, run_id="run_ghost"
            )

    def test_unfinished_run_id_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        add_run(
            conn,
            run_id="run_a",
            started_at="2026-01-01T00:00:00",
            status="running",
            render_ref="doc1/render/document/doc1/a.json",
        )
        conn.close()
        with pytest.raises(run_module.RunResolutionError, match="not complete"):
            run_module.resolve_run(
                registry_path, "doc1", artifact_root=artifact_root, run_id="run_a"
            )

    def test_failed_run_not_picked_as_latest(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        """A failed run must not be selected as the default latest complete run."""
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        add_run(
            conn,
            run_id="run_failed",
            started_at="2026-03-01T00:00:00",
            status="failed",
            render_ref="doc1/render/document/doc1/f.json",
        )
        conn.close()
        with pytest.raises(run_module.RunResolutionError, match="No complete runs"):
            run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root, edition="en")

    def test_run_without_render_artifact_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        # render_ref=NO_RENDER → no render stage event recorded for the run
        add_run(conn, run_id="run_a", started_at="2026-01-01T00:00:00", render_ref=NO_RENDER)
        conn.close()
        with pytest.raises(run_module.RunResolutionError, match="no render artifact"):
            run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)

    def test_missing_render_file_on_disk_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        add_run(
            conn,
            run_id="run_a",
            started_at="2026-01-01T00:00:00",
            render_ref="doc1/render/document/doc1/gone.json",
        )
        conn.close()
        # render result file is never written to disk
        with pytest.raises(run_module.RunResolutionError, match="missing on disk"):
            run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)

    def test_missing_qa_summary_file_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        """A run advertising a qa_summary whose file is gone must refuse, not fall back."""
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        ref = "doc1/render/document/doc1/a.json"
        add_run(
            conn,
            run_id="run_a",
            started_at="2026-01-01T00:00:00",
            render_ref=ref,
            qa_summary_ref="doc1/qa/document/doc1/gone.json",
        )
        conn.close()
        write_render_result(artifact_root, ref, {"page_refs": {"p0001": "x.json"}})

        resolved = run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)
        with pytest.raises(run_module.RunResolutionError, match="QA summary"):
            run_module.resolve_qa_summary_path(resolved, artifact_root)

    def test_missing_page_artifact_refuses(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        """load_run_pages refuses when a page_ref points at a missing file."""
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        ref = "doc1/render/document/doc1/a.json"
        add_run(conn, run_id="run_a", started_at="2026-01-01T00:00:00", render_ref=ref)
        conn.close()
        write_render_result(
            artifact_root, ref, {"page_refs": {"p0001": "doc1/render_page.v1/page/p0001/gone.json"}}
        )
        resolved = run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)
        with pytest.raises(run_module.RunResolutionError, match="missing"):
            run_module.load_run_pages(resolved, artifact_root)


class TestCrossRunIsolation:
    def test_two_runs_cannot_splice(self, repo: tuple[Path, Path], run_module: ModuleType) -> None:
        """Resolving run A never pulls in run B's artifacts (the splice hazard)."""
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        ref_a = "doc1/render/document/doc1/a.json"
        ref_b = "doc1/render/document/doc1/b.json"
        add_run(
            conn,
            run_id="run_a",
            started_at="2026-01-01T00:00:00",
            render_ref=ref_a,
            git_commit="commit_a",
            qa_summary_ref="doc1/qa/document/doc1/qa_a.json",
        )
        add_run(
            conn,
            run_id="run_b",
            started_at="2026-02-01T00:00:00",
            render_ref=ref_b,
            git_commit="commit_b",
            qa_summary_ref="doc1/qa/document/doc1/qa_b.json",
        )
        conn.close()
        write_render_result(
            artifact_root,
            ref_a,
            {
                "page_refs": {"p0001": "A/p0001.json"},
                "glossary_ref": "A/glossary.json",
            },
        )
        write_render_result(
            artifact_root,
            ref_b,
            {
                "page_refs": {"p0001": "B/p0001.json"},
                "glossary_ref": "B/glossary.json",
            },
        )

        resolved_a = run_module.resolve_run(
            registry_path, "doc1", artifact_root=artifact_root, run_id="run_a"
        )
        # Every artifact ref must come from run A — none from run B.
        assert resolved_a.git_commit == "commit_a"
        assert resolved_a.page_refs == {"p0001": "A/p0001.json"}
        assert resolved_a.glossary_ref == "A/glossary.json"
        assert resolved_a.qa_summary_ref == "doc1/qa/document/doc1/qa_a.json"
        assert "B/" not in resolved_a.glossary_ref
        assert all("B/" not in v for v in resolved_a.page_refs.values())

    def test_re_resolve_same_run_is_identical(
        self, repo: tuple[Path, Path], run_module: ModuleType
    ) -> None:
        """Resolving the same run twice yields identical refs (deterministic)."""
        registry_path, artifact_root = repo
        conn = init_registry(registry_path)
        ref = "doc1/render/document/doc1/a.json"
        add_run(conn, run_id="run_a", started_at="2026-01-01T00:00:00", render_ref=ref)
        conn.close()
        write_render_result(artifact_root, ref, {"page_refs": {"p0001": "x.json"}})

        first = run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)
        second = run_module.resolve_run(registry_path, "doc1", artifact_root=artifact_root)
        assert first.model_dump() == second.model_dump()
