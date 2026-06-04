"""End-to-end ref-binding success criteria for `make export` (S5U-869).

Drives ``export_to_web.main()`` against a registry + artifact store fixture and
asserts the three issue success criteria:

* Exporting twice from the same run is byte-identical.
* A repo with two runs cannot produce a cross-run spliced bundle.
* Provenance (run_id, git_commit) is present in the exported bundle.

Plus the must-not-break edition-isolation invariant: an EN run's page_refs only
point at EN render pages, so the EN bundle can never include RU content.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ._export_run_fixtures import add_run, init_registry, write_render_result

REPO = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "export_to_web.py"


@pytest.fixture()
def export_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[ModuleType]:
    """Import export_to_web.py with ARTIFACT_ROOT/REGISTRY_PATH/doc_public redirected to tmp."""
    sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
    sys.path.insert(0, str(SCRIPTS_DIR))
    # The S5U-870 blocking-QA gate reads the QA config via _export_qa_gate; patch
    # it to the default so the fake "doc1" needs no real document config. These
    # tests seed a non-blocking QA summary (see _seed_run) so the gate allows.
    gate_spec = importlib.util.spec_from_file_location(
        "_export_qa_gate", SCRIPTS_DIR / "_export_qa_gate.py"
    )
    assert gate_spec is not None and gate_spec.loader is not None
    gate_mod = importlib.util.module_from_spec(gate_spec)
    sys.modules["_export_qa_gate"] = gate_mod
    gate_spec.loader.exec_module(gate_mod)
    monkeypatch.setattr(gate_mod, "resolve_block_on", lambda doc_id: {"error", "critical"})

    spec = importlib.util.spec_from_file_location("export_to_web", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_to_web"] = mod
    spec.loader.exec_module(mod)

    artifact_root = tmp_path / "artifacts"
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"
    documents_root.mkdir(parents=True)
    monkeypatch.setattr(mod, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(mod, "REGISTRY_PATH", tmp_path / "registry.db")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    # Skip PDF image extraction (no PDF in the fixture) and facsimile override config.
    monkeypatch.setattr(mod, "extract_images", lambda *a, **k: {})
    monkeypatch.setattr(mod, "_load_facsimile_override_pids", lambda doc_id: [])
    yield mod
    sys.modules.pop("export_to_web", None)
    sys.modules.pop("_export_qa_gate", None)


def _seed_run(  # noqa: PLR0913 — keyword-only test fixture builder
    artifact_root: Path,
    conn: sqlite3.Connection,
    *,
    run_id: str,
    started_at: str,
    edition: str,
    git_commit: str,
    page_text: str,
    page_ids: tuple[str, ...] = ("p0001",),
    with_qa: bool = True,
    with_glossary: bool = False,
) -> None:
    """Seed a complete run: render result + page artifacts + registry rows.

    Built on the shared ``_export_run_fixtures`` scaffolding; this only adds the
    on-disk render-page payloads the exporter renders into the bundle.

    ``with_qa`` / ``with_glossary`` (S5U-892) toggle whether the run carries a
    QA summary / glossary artifact, so a test can model a run B that lacks the
    companions a run A wrote and assert the re-export removes the stale files.
    """
    render_ref = f"doc1/render/document/doc1/{run_id}.json"
    page_refs: dict[str, str] = {}
    for pid in page_ids:
        page_ref = f"doc1/render_page.v1/page/{pid}/{run_id}.json"
        page_refs[pid] = page_ref
        page_path = artifact_root / page_ref
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "document_version": edition,
                    "page": {"page_id": pid, "title": f"Page {pid}"},
                    "blocks": [
                        {
                            "kind": "paragraph",
                            "id": f"{pid}.b0",
                            "children": [{"kind": "text", "text": page_text}],
                        }
                    ],
                }
            )
        )
    render_result: dict[str, object] = {"page_refs": page_refs}
    if with_glossary:
        glossary_ref = f"doc1/glossary/document/doc1/{run_id}.json"
        render_result["glossary_ref"] = glossary_ref
        glossary_path = artifact_root / glossary_ref
        glossary_path.parent.mkdir(parents=True, exist_ok=True)
        glossary_path.write_text(
            json.dumps({"entries": [{"term": f"term-{run_id}", "definition": page_text}]})
        )
    write_render_result(artifact_root, render_ref, render_result)
    qa_ref: str | None = None
    if with_qa:
        # Attach a non-blocking QA summary so the S5U-870 export gate allows;
        # these tests exercise ref-binding, not the QA gate (the gate has its own
        # suite in test_export_qa_gate.py).
        qa_ref = f"doc1/qa/document/doc1/{run_id}.json"
        qa_path = artifact_root / qa_ref
        qa_path.parent.mkdir(parents=True, exist_ok=True)
        qa_path.write_text(
            json.dumps(
                {
                    "schema_version": "qa_summary.v1",
                    "document_id": "doc1",
                    "run_id": run_id,
                    "edition": edition,
                    "blocking": False,
                    "record_refs": [],
                    "review_pack_ref": "",
                }
            )
        )
    add_run(
        conn,
        run_id=run_id,
        started_at=started_at,
        edition=edition,
        git_commit=git_commit,
        render_ref=render_ref,
        qa_summary_ref=qa_ref,
    )


def _read_bundle(documents_root: Path, edition: str) -> dict[str, str]:
    """Read every file under the edition bundle into {relpath: text} for comparison."""
    base = documents_root / "doc1"
    out: dict[str, str] = {}
    for p in sorted((base / edition).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(base))] = p.read_text()
    return out


def test_export_twice_same_run_is_byte_identical(export_module: ModuleType, tmp_path: Path) -> None:
    """Success criterion: re-exporting the same run produces an identical bundle."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="commit_a",
        page_text="Example",
    )
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    export_module.main(["--doc", "doc1", "--edition", "en"])
    first = _read_bundle(documents_root, "en")
    export_module.main(["--doc", "doc1", "--edition", "en"])
    second = _read_bundle(documents_root, "en")

    assert first == second
    assert first  # non-empty


def test_provenance_present_in_bundle(export_module: ModuleType, tmp_path: Path) -> None:
    """Success criterion: run_id + git_commit are stamped into the bundle manifest."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_prov",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="cafebabe1234",
        page_text="Example",
    )
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    export_module.main(["--doc", "doc1", "--edition", "en"])

    manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert manifest["provenance"]["run_id"] == "run_prov"
    assert manifest["provenance"]["git_commit"] == "cafebabe1234"
    assert manifest["provenance"]["edition"] == "en"


def test_two_runs_no_cross_run_splice(export_module: ModuleType, tmp_path: Path) -> None:
    """Success criterion: a repo with two runs binds the bundle to ONE run only."""
    conn = init_registry(tmp_path / "registry.db")
    # Older run A and newer run B, both EN. The latest-complete default picks B.
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="commit_a",
        page_text="OLD-A-CONTENT",
    )
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_b",
        started_at="2026-02-01T00:00:00",
        edition="en",
        git_commit="commit_b",
        page_text="NEW-B-CONTENT",
    )
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    export_module.main(["--doc", "doc1", "--edition", "en"])

    manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert manifest["provenance"]["run_id"] == "run_b"
    page = json.loads(
        (documents_root / "doc1" / "en" / "data" / "render_page.p0001.json").read_text()
    )
    text = page["blocks"][0]["children"][0]["text"]
    # Page content comes from run B only — never spliced with run A.
    assert text == "NEW-B-CONTENT"

    # Pinning --run-id=run_a yields A's content + provenance (explicit override).
    export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    manifest_a = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert manifest_a["provenance"]["run_id"] == "run_a"
    page_a = json.loads(
        (documents_root / "doc1" / "en" / "data" / "render_page.p0001.json").read_text()
    )
    assert page_a["blocks"][0]["children"][0]["text"] == "OLD-A-CONTENT"


def test_reexport_removes_stale_companions_when_run_b_lacks_them(
    export_module: ModuleType, tmp_path: Path
) -> None:
    """S5U-892: a ref-bound re-export must delete companion files the bound run lacks.

    Run A carries a glossary; run B does not (but carries QA, so the S5U-870
    fail-closed export gate allows the export — a run with *no* QA summary is
    refused upstream by that gate, so the glossary/metrics leftovers are the
    reachable cross-run-splice surface here). Exporting B (latest-complete
    default) must remove run A's ``glossary.json`` and the stale
    ``qa_metrics.json`` from the edition data dir, otherwise the reader (which
    fetches fixed paths) splices run-A glossary/metrics over run-B's pages.
    """
    conn = init_registry(tmp_path / "registry.db")
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="commit_a",
        page_text="OLD-A-CONTENT",
        with_qa=True,
        with_glossary=True,
    )
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"
    data_dir = documents_root / "doc1" / "en" / "data"

    # Export run A: glossary present.
    export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    assert (data_dir / "glossary.json").exists()
    # Seed a stale qa_metrics.json as if run A had emitted metrics (the seeded
    # summary carries no metrics ref, so the exporter never writes one — we plant
    # it directly to model the prior-run leftover the cleanup must remove).
    (data_dir / "qa_metrics.json").write_text(json.dumps({"run_id": "run_a"}))

    # Add the newer run B with QA but NO glossary, then re-export (default
    # latest-complete resolves to run B).
    conn = sqlite3.connect(str(tmp_path / "registry.db"))
    conn.row_factory = sqlite3.Row
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_b",
        started_at="2026-02-01T00:00:00",
        edition="en",
        git_commit="commit_b",
        page_text="NEW-B-CONTENT",
        with_qa=True,
        with_glossary=False,
    )
    conn.close()

    export_module.main(["--doc", "doc1", "--edition", "en"])

    manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert manifest["provenance"]["run_id"] == "run_b"
    # Run B's QA summary is exported fresh (overwrites run A's in place).
    assert (data_dir / "qa_summary.json").exists()
    # The stale run-A companions B does not carry must be GONE — not spliced.
    assert not (data_dir / "glossary.json").exists()
    assert not (data_dir / "qa_metrics.json").exists()


def test_edition_isolation_en_excludes_ru(export_module: ModuleType, tmp_path: Path) -> None:
    """Must-not-break: an EN run's pages carry no RU content (edition isolation)."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_en",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="c_en",
        page_text="English only",
    )
    _seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_ru",
        started_at="2026-02-01T00:00:00",
        edition="ru",
        git_commit="c_ru",
        page_text="Только русский",
    )
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    # EN export must resolve the EN run (not the newer RU run) and carry no Cyrillic.
    export_module.main(["--doc", "doc1", "--edition", "en"])
    manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert manifest["provenance"]["run_id"] == "run_en"
    page = json.loads(
        (documents_root / "doc1" / "en" / "data" / "render_page.p0001.json").read_text()
    )
    text = page["blocks"][0]["children"][0]["text"]
    assert text == "English only"
    assert not any("Ѐ" <= ch <= "ӿ" for ch in text)


def test_missing_run_exits_nonzero(export_module: ModuleType, tmp_path: Path) -> None:
    """G1: an empty registry makes main() exit non-zero (no partial bundle)."""
    init_registry(tmp_path / "registry.db").close()
    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
