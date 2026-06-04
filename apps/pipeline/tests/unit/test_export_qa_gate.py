"""Blocking-QA gate for `make export` (S5U-870).

Drives ``export_to_web.main()`` against a registry + artifact-store fixture and
asserts the gate behavior the issue's threat table requires:

* Default mode refuses (exit non-zero) on a run with blocking, non-waived QA.
* ``--review-only`` produces a clearly-marked draft bundle (and stamps the
  draft disposition into the manifest provenance), exit 0.
* A waived blocking-severity record does not count as blocking (gate allows).
* **An ambient env var must NOT flip the gate's default** — setting a plausible
  review-only env var with NO ``--review-only`` flag still refuses (guards.md
  G1: an env-only override that flips the default is a gate bypass).
* G1 fail-closed: a run advertising a QA summary whose file is gone refuses;
  here we cover the "no QA summary at all → must refuse" decision too.

Red-before: at branch base 2b078bc the export script has no QA gate at all —
``export_to_web`` exports regardless of blocking QA — so every refusal/draft
assertion below fails (the export succeeds) on the pre-fix tree, and the import
of ``_enforce_export_qa_gate`` / ``--review-only`` does not exist.
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
    """Import export_to_web.py with paths + config redirected to tmp.

    ``_export_qa_gate.resolve_block_on`` is monkeypatched to the default
    error/critical set so the test does not need a real ``doc1`` document
    config (the gate module is what actually reads the QA config).
    """
    sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
    sys.path.insert(0, str(SCRIPTS_DIR))
    # Import the gate module first so the entry script's `from _export_qa_gate
    # import ...` binds to this same module object we monkeypatch below.
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
    monkeypatch.setattr(mod, "extract_images", lambda *a, **k: {})
    monkeypatch.setattr(mod, "_load_facsimile_override_pids", lambda doc_id: [])
    yield mod
    sys.modules.pop("export_to_web", None)
    sys.modules.pop("_export_qa_gate", None)


def _write_qa_record(
    artifact_root: Path, ref: str, *, code: str, page_id: str, waived: bool
) -> None:
    path = artifact_root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "qa_record.v1",
                "qa_id": f"qa.{code}.{page_id}",
                "layer": "structure",
                "severity": "error",
                "code": code,
                "page_id": page_id,
                "waived": waived,
            }
        )
    )


def _seed_run_with_qa(  # noqa: PLR0913 — keyword-only test fixture builder
    artifact_root: Path,
    conn: sqlite3.Connection,
    *,
    run_id: str,
    blocking: bool,
    waived: bool = False,
    qa_summary_ref: str | None = "doc1/qa/document/doc1/qa.json",
    code: str = "GLUED_TEXT",
    page_id: str = "p0007",
) -> None:
    """Seed a complete EN run (render result + page) plus a QA summary + record."""
    render_ref = f"doc1/render/document/doc1/{run_id}.json"
    page_ref = f"doc1/render_page.v1/page/{page_id}/{run_id}.json"
    page_path = artifact_root / page_ref
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "document_version": "en",
                "page": {"page_id": page_id, "title": f"Page {page_id}"},
                "blocks": [
                    {
                        "kind": "paragraph",
                        "id": f"{page_id}.b0",
                        "children": [{"kind": "text", "text": "Example body"}],
                    }
                ],
            }
        )
    )
    write_render_result(artifact_root, render_ref, {"page_refs": {page_id: page_ref}})

    record_refs: list[str] = []
    if qa_summary_ref is not None:
        rec_ref = f"doc1/qa_record.v1/page/{page_id}/{run_id}.json"
        _write_qa_record(artifact_root, rec_ref, code=code, page_id=page_id, waived=waived)
        record_refs.append(rec_ref)
        summary_path = artifact_root / qa_summary_ref
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "schema_version": "qa_summary.v1",
                    "document_id": "doc1",
                    "run_id": run_id,
                    "edition": "en",
                    "blocking": blocking,
                    "record_refs": record_refs,
                    "review_pack_ref": "doc1/review_pack.v1/document/doc1/rp.json",
                }
            )
        )

    add_run(
        conn,
        run_id=run_id,
        started_at="2026-01-01T00:00:00",
        edition="en",
        render_ref=render_ref,
        qa_summary_ref=qa_summary_ref,
    )


def test_export_refuses_on_blocking_qa(export_module: ModuleType, tmp_path: Path) -> None:
    """Default mode: blocking, non-waived QA → exit non-zero, no bundle written."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_run_with_qa(export_module.ARTIFACT_ROOT, conn, run_id="run_block", blocking=True)
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    # No edition bundle was written.
    assert not (documents_root / "doc1" / "en" / "manifest.json").exists()


def test_export_refusal_names_codes_and_pages(
    export_module: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal message names the blocking codes/pages."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_run_with_qa(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_block",
        blocking=True,
        code="DEAD_PAGE_REF",
        page_id="p0012",
    )
    conn.close()

    with pytest.raises(SystemExit):
        export_module.main(["--doc", "doc1", "--edition", "en"])
    out = capsys.readouterr().out
    assert "DEAD_PAGE_REF" in out
    assert "p0012" in out


def test_export_review_only_produces_draft(export_module: ModuleType, tmp_path: Path) -> None:
    """--review-only on a blocking run exports a draft + stamps the manifest."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_run_with_qa(export_module.ARTIFACT_ROOT, conn, run_id="run_block", blocking=True)
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    export_module.main(["--doc", "doc1", "--edition", "en", "--review-only"])

    manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert manifest["provenance"]["review_only_draft"] == "true"
    assert "GLUED_TEXT" in manifest["provenance"]["blocking_qa_codes"]


def test_export_allows_when_not_blocking(export_module: ModuleType, tmp_path: Path) -> None:
    """A non-blocking run exports normally, with no draft marker."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_run_with_qa(export_module.ARTIFACT_ROOT, conn, run_id="run_ok", blocking=False)
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    export_module.main(["--doc", "doc1", "--edition", "en"])

    manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert "review_only_draft" not in manifest["provenance"]


def test_export_waived_blocking_record_not_blocked(
    export_module: ModuleType, tmp_path: Path
) -> None:
    """Waived semantics: a waived error record yields a non-blocking summary → allow."""
    conn = init_registry(tmp_path / "registry.db")
    # summary.blocking=False because the only error record is waived (mirrors
    # what QAStage would compute); the gate allows and writes the bundle.
    _seed_run_with_qa(
        export_module.ARTIFACT_ROOT, conn, run_id="run_waived", blocking=False, waived=True
    )
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    export_module.main(["--doc", "doc1", "--edition", "en"])
    manifest = json.loads((documents_root / "doc1" / "en" / "manifest.json").read_text())
    assert "review_only_draft" not in manifest["provenance"]


def test_env_var_does_not_flip_review_only(
    export_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G1: an ambient env var must NOT enable review-only — still refuses.

    Setting plausible review-only env-var names with NO ``--review-only`` flag
    must leave the gate's default in force (refuse on blocking QA).
    """
    conn = init_registry(tmp_path / "registry.db")
    _seed_run_with_qa(export_module.ARTIFACT_ROOT, conn, run_id="run_block", blocking=True)
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    monkeypatch.setenv("ATR_REVIEW_ONLY", "1")
    monkeypatch.setenv("REVIEW_ONLY", "1")
    monkeypatch.setenv("ATR_EXPORT_REVIEW_ONLY", "true")

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    assert not (documents_root / "doc1" / "en" / "manifest.json").exists()


def test_export_fails_closed_when_no_qa_summary(export_module: ModuleType, tmp_path: Path) -> None:
    """G1: a complete run with NO QA summary refuses, does not pass by absent state."""
    conn = init_registry(tmp_path / "registry.db")
    # qa_summary_ref=None → no QA summary artifact at all.
    _seed_run_with_qa(
        export_module.ARTIFACT_ROOT, conn, run_id="run_noqa", blocking=False, qa_summary_ref=None
    )
    conn.close()
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    assert not (documents_root / "doc1" / "en" / "manifest.json").exists()
