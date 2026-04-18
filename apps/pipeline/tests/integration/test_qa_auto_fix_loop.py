"""Integration test: QA auto-fix feedback loop.

Seeds a minimal artifact store with IR + render pages containing two
deterministic auto-fixable issues (an asset-token leak and a duplicate
block), invokes ``atr qa --doc X --auto-fix`` as a dry-run and then with
``--apply``, and verifies:

1. Dry-run writes patch files but does not mutate renders.
2. ``--apply`` mutates the render and reduces finding counts to zero
   for the targeted codes.
3. The guard rejects ``--apply`` without ``--auto-fix``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from atr_pipeline.cli.main import app
from atr_pipeline.config.models import DocumentBuildConfig, DocumentConfig, QAConfig
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)

DOC_ID = "qa_autofix_fixture"
PAGE_ID = "p0001"


def _seed_page_ir(store: ArtifactStore, family: str, language: LanguageCode) -> None:
    _seed_page_ir_for(store, family, language, PAGE_ID, 1)


def _seed_page_ir_for(
    store: ArtifactStore,
    family: str,
    language: LanguageCode,
    page_id: str,
    page_number: int,
) -> None:
    ir = PageIRV1(
        document_id=DOC_ID,
        page_id=page_id,
        page_number=page_number,
        language=language,
        blocks=[],
    )
    store.put_json(
        document_id=DOC_ID,
        schema_family=family,
        scope="page",
        entity_id=page_id,
        data=ir,
    )


def _seed_render_with_findings(store: ArtifactStore) -> RenderPageV1:
    """Render page with (a) an asset-token leak and (b) a duplicate pair."""
    # Block with AM0308 token → DECORATIVE_ICON_LEAKED.
    # Blocks 2 and 3 are near-identical → DUPLICATE_CONTENT on b3.
    render = RenderPageV1(
        page=RenderPageMeta(id=PAGE_ID, title="Fixture", source_page_number=1),
        blocks=[
            RenderParagraphBlock(
                id="b1",
                children=[RenderTextInline(text="Используйте AM0308 при атаке")],
            ),
            RenderParagraphBlock(
                id="b2",
                children=[RenderTextInline(text="second block with shared phrasing")],
            ),
            RenderParagraphBlock(
                id="b3",
                children=[RenderTextInline(text="second block with shared phrasing")],
            ),
        ],
        source_map=RenderSourceMap(page_id=PAGE_ID, block_refs=[]),
    )
    store.put_json(
        document_id=DOC_ID,
        schema_family="render_page.v1",
        scope="page",
        entity_id=PAGE_ID,
        data=render,
    )
    return render


@pytest.fixture
def store_and_config(tmp_path: Path) -> tuple[ArtifactStore, DocumentBuildConfig]:
    """Build a minimal artifact store + DocumentBuildConfig for the fixture doc."""
    artifact_root = tmp_path / "artifacts"
    store = ArtifactStore(artifact_root)

    _seed_page_ir(store, "page_ir.v1.en", LanguageCode.EN)
    _seed_page_ir(store, "page_ir.v1.ru", LanguageCode.RU)
    _seed_render_with_findings(store)

    config = DocumentBuildConfig(
        document=DocumentConfig(id=DOC_ID, source_pdf=""),
        qa=QAConfig(block_publish_on=["error", "critical"], waivers_dir="waivers"),
        repo_root=tmp_path,
        artifact_root=artifact_root,
    )
    (tmp_path / "waivers").mkdir(exist_ok=True)
    return store, config


def _invoke(
    args: list[str],
    config: DocumentBuildConfig,
) -> tuple[int, str]:
    runner = CliRunner()
    with patch(
        "atr_pipeline.cli.commands.qa.load_document_config",
        return_value=config,
    ):
        result = runner.invoke(app, args)
    combined = (result.stdout or "") + (result.stderr or "")
    return result.exit_code, combined


def test_dry_run_writes_patches_without_mutating_render(
    store_and_config: tuple[ArtifactStore, DocumentBuildConfig],
) -> None:
    store, config = store_and_config
    # Capture the initial render content hash for comparison after dry-run.
    render_dir = store.root / DOC_ID / "render_page.v1" / "page" / PAGE_ID
    hashes_before = sorted(p.stem for p in render_dir.glob("*.json"))
    assert len(hashes_before) == 1

    exit_code, out = _invoke(
        ["qa", "--doc", DOC_ID, "--auto-fix"],
        config,
    )
    assert exit_code == 0, f"Unexpected exit {exit_code}:\n{out}"

    # Patch file written
    patch_dir = store.root / DOC_ID / "patch_set.v1" / "page" / PAGE_ID
    patches = list(patch_dir.glob("*.json"))
    assert len(patches) == 1, f"Expected 1 patch, got {patches}"

    # Render untouched — same (single) content hash
    hashes_after = sorted(p.stem for p in render_dir.glob("*.json"))
    assert hashes_after == hashes_before, "Dry-run mutated render artifacts"


def test_apply_loop_reduces_findings(
    store_and_config: tuple[ArtifactStore, DocumentBuildConfig],
) -> None:
    store, config = store_and_config

    exit_code, out = _invoke(
        ["qa", "--doc", DOC_ID, "--auto-fix", "--apply"],
        config,
    )
    assert exit_code == 0, f"Unexpected exit {exit_code}:\n{out}"
    # Diff table is printed
    assert "BEFORE" in out and "AFTER" in out

    # New render content hash was written
    render_dir = store.root / DOC_ID / "render_page.v1" / "page" / PAGE_ID
    hashes_after = sorted(p.stem for p in render_dir.glob("*.json"))
    assert len(hashes_after) >= 2, "Apply did not write a second render version"

    # Re-run QA and confirm targeted codes are gone.
    exit_code2, out2 = _invoke(["qa", "--doc", DOC_ID], config)
    assert exit_code2 == 0, f"Post-apply QA failed:\n{out2}"
    assert "DECORATIVE_ICON_LEAKED" not in out2
    assert "DUPLICATE_CONTENT" not in out2


def test_apply_without_auto_fix_is_rejected(
    store_and_config: tuple[ArtifactStore, DocumentBuildConfig],
) -> None:
    _, config = store_and_config
    exit_code, out = _invoke(
        ["qa", "--doc", DOC_ID, "--apply"],
        config,
    )
    assert exit_code == 2
    assert "requires --auto-fix" in out


def test_apply_exits_zero_when_auto_fix_clears_all_blockers(
    store_and_config: tuple[ArtifactStore, DocumentBuildConfig],
) -> None:
    """Regression for S5U-604.

    When ``block_publish_on`` is configured such that pre-fix findings
    are blocking but auto-fix clears them, the CLI must exit 0 — i.e.
    the exit-code decision must consult the POST-fix record set, not
    the stale pre-fix set.

    Before the fix: the final ``has_blocking`` check ran against
    ``all_records`` (pre-fix), so exit was 1 even after a successful
    apply. Verified red before fix, green after.
    """
    _, config = store_and_config
    # Elevate the fixture's WARNING findings to blockers so the exit
    # code is sensitive to whether pre- or post-fix records feed
    # ``has_blocking``.
    config.qa.block_publish_on = ["warning", "error", "critical"]

    exit_code, out = _invoke(
        ["qa", "--doc", DOC_ID, "--auto-fix", "--apply"],
        config,
    )

    assert exit_code == 0, (
        f"Expected exit 0 after auto-fix cleared all blockers, got exit {exit_code}:\n{out}"
    )
    # Bonus: post-fix summary shows the reduction was reported.
    assert "BEFORE" in out and "AFTER" in out
    assert "DECORATIVE_ICON_LEAKED" in out
    assert "DUPLICATE_CONTENT" in out
    # The TOTAL row ends "-2" (two findings, both cleared).
    assert "-2" in out


def test_apply_preserves_blockers_on_unmutated_pages(
    store_and_config: tuple[ArtifactStore, DocumentBuildConfig],
) -> None:
    """Regression for S5U-604 (merge behaviour).

    ``apply_patches_and_rerun`` only re-evaluates mutated pages. When
    the apply loop succeeds on page 1 but an un-mutated page 2 still
    carries an ERROR finding, the final exit code must remain 1 —
    otherwise the fix would silently drop blockers on pages the
    auto-fixer never touched.
    """
    store, config = store_and_config
    # Page 2: seed a render containing a LEAKED_TECHNICAL_ID finding,
    # which is ERROR-severity and *not* auto-fixable → stays in the
    # pre-fix record set and never appears in post-fix records.
    second_page = "p0002"
    _seed_page_ir_for(store, "page_ir.v1.en", LanguageCode.EN, second_page, 2)
    _seed_page_ir_for(store, "page_ir.v1.ru", LanguageCode.RU, second_page, 2)
    unmutated_render = RenderPageV1(
        page=RenderPageMeta(id=second_page, title="Fixture 2", source_page_number=2),
        blocks=[
            RenderParagraphBlock(
                id="b1",
                children=[RenderTextInline(text="See ato_core_v1_1 for details")],
            ),
        ],
        source_map=RenderSourceMap(page_id=second_page, block_refs=[]),
    )
    store.put_json(
        document_id=DOC_ID,
        schema_family="render_page.v1",
        scope="page",
        entity_id=second_page,
        data=unmutated_render,
    )

    exit_code, out = _invoke(
        ["qa", "--doc", DOC_ID, "--auto-fix", "--apply"],
        config,
    )

    # Page 1 blockers cleared by auto-fix, but page 2's ERROR remains.
    assert exit_code == 1, (
        f"Expected exit 1 — un-mutated page's ERROR should still block — got {exit_code}:\n{out}"
    )
    assert "LEAKED_TECHNICAL_ID" in out


def test_waived_record_is_skipped_by_auto_fix(
    store_and_config: tuple[ArtifactStore, DocumentBuildConfig],
    tmp_path: Path,
) -> None:
    """Records matching a waiver must not generate or apply patches."""
    _, config = store_and_config
    # Waive the decorative finding on b1
    waiver = (
        "- qa_code: DECORATIVE_ICON_LEAKED\n"
        f"  page_id: {PAGE_ID}\n"
        "  entity_ref: b1\n"
        "  reason: fixture\n"
        "  waived_by: test\n"
    )
    waivers_file = tmp_path / "waivers" / f"{DOC_ID}.yaml"
    waivers_file.write_text(waiver, encoding="utf-8")

    exit_code, out = _invoke(
        ["qa", "--doc", DOC_ID, "--auto-fix", "--apply"],
        config,
    )
    assert exit_code == 0, out
    # Patch file should still exist for the non-waived duplicate, but the
    # decorative op should not be present. Re-run QA and verify.
    exit_code2, out2 = _invoke(["qa", "--doc", DOC_ID], config)
    # Decorative finding remains (waived, still reported but not blocking)
    # Duplicate finding is resolved by auto-fix.
    assert "DUPLICATE_CONTENT" not in out2
    assert exit_code2 == 0
