"""S5U-1221 — ``IngestStage.extra_cache_inputs`` folds the source-PDF
content hash into the ingest cache key.

The ingest cache key previously held only the config hash, which carries the
PDF *path*, not its *bytes* (``fingerprint_pdf`` runs only inside ``run()``,
i.e. on a cache miss). Swapping the PDF at the configured path therefore
cache-hit the stale ``SourceManifestV1`` and the whole downstream chain
silently reflected the previous PDF. ``extra_cache_inputs`` closes this by
hashing the file at ``ctx.config.source_pdf_path`` into the cache key so a
replaced PDF invalidates ingest and the downstream chain.

Three assertions (three-input discipline):

* happy/stable — unchanged PDF bytes produce a stable ``pdf_sha256:<hash>``
  entry across calls;
* failure/changed — different PDF bytes at the same path produce a different
  entry;
* adversarial/missing — a missing PDF returns the ``pdf_sha256:missing``
  sentinel without raising (``run()`` remains the authoritative failure point).
"""

from __future__ import annotations

from pathlib import Path

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import start_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.ingest.stage import IngestStage
from atr_pipeline.store.artifact_store import ArtifactStore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ctx(tmp_path: Path, pdf_path: Path) -> StageContext:
    """Build a StageContext whose config points ``source_pdf`` at ``pdf_path``.

    ``source_pdf`` is stored as an absolute string so
    ``DocumentBuildConfig.source_pdf_path`` resolves to ``pdf_path`` directly.
    """
    config = load_document_config("walking_skeleton", repo_root=_repo_root())
    config.document.source_pdf = str(pdf_path)
    store = ArtifactStore(tmp_path / "artifacts")
    conn = open_registry(tmp_path / "registry.db")
    start_run(
        conn,
        run_id="ingest_pdf_content",
        document_id="walking_skeleton",
        pipeline_version="0.1.0",
        config_hash="test",
    )
    return StageContext(
        run_id="ingest_pdf_content",
        document_id="walking_skeleton",
        config=config,
        artifact_store=store,
        registry_conn=conn,
        repo_root=_repo_root(),
    )


def test_extra_cache_inputs_changes_with_pdf_bytes(tmp_path: Path) -> None:
    """A different PDF byte-payload at the same path yields a different
    ``pdf_sha256:<hash>`` cache-input entry; identical bytes stay stable.
    """
    pdf_path = tmp_path / "source.pdf"

    pdf_path.write_bytes(b"%PDF-1.4 first payload\n")
    first = IngestStage().extra_cache_inputs(_make_ctx(tmp_path / "a", pdf_path))
    first_again = IngestStage().extra_cache_inputs(_make_ctx(tmp_path / "b", pdf_path))

    pdf_path.write_bytes(b"%PDF-1.4 second payload (different)\n")
    second = IngestStage().extra_cache_inputs(_make_ctx(tmp_path / "c", pdf_path))

    assert len(first) == 1
    assert first[0].startswith("pdf_sha256:")
    # Stable for unchanged bytes.
    assert first == first_again
    # Changes when the bytes change.
    assert first != second
    assert second[0].startswith("pdf_sha256:")


def test_extra_cache_inputs_missing_pdf_returns_sentinel(tmp_path: Path) -> None:
    """A missing source PDF yields the ``pdf_sha256:missing`` sentinel rather
    than raising — ``run()`` remains the authoritative FileNotFoundError site.
    """
    missing_pdf = tmp_path / "does_not_exist.pdf"
    assert not missing_pdf.exists()

    result = IngestStage().extra_cache_inputs(_make_ctx(tmp_path / "ctx", missing_pdf))

    assert result == ["pdf_sha256:missing"]
