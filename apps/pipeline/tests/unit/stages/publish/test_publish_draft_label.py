"""S5U-894: PublishStage stamps the loud review-only draft label into its manifest.

On a ``--review-only`` draft built over blocking QA, the published
``BuildManifestV1`` must be self-describing on disk (``review_only_draft=true`` +
the blocking codes + the review-pack ref) so a downstream consumer can tell the
bundle MUST NOT be released — matching ``make export``'s stamped provenance
(``stamp_draft_provenance``). These tests pin that the two publish surfaces agree
and that the manifest label survives the executor cache (version bumped 1.1 ->
1.2 in the same change, per ``.claude/rules/pipeline.md``).

Shared fixtures live in ``_publish_fixtures.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from atr_pipeline.runner.executor import execute_stage
from atr_pipeline.stages.publish.qa_gate import QAGateResult
from atr_pipeline.stages.publish.stage import PublishStage

from ._publish_fixtures import (
    make_ctx,
    read_manifest,
    repo_root,
    run_prerequisites,
    seed_blocking_summary,
)


def _load_export_gate_module() -> ModuleType:
    """Import ``scripts/_export_qa_gate.py`` (mirrors the export-path test setup).

    The export gate module uses sibling imports (``from _export_run import ...``),
    so ``scripts/`` must be on ``sys.path`` before loading it. Used to assert the
    PublishStage and ``make export`` draft labels agree (S5U-894).
    """
    scripts_dir = repo_root() / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "_export_qa_gate", scripts_dir / "_export_qa_gate.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_qa_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_publish_review_only_stamps_draft_label_into_manifest(tmp_path: Path) -> None:
    """A review-only draft's on-disk BuildManifestV1 is self-describing (S5U-894).

    The manifest must carry ``review_only_draft=true``, the blocking codes, and
    the review-pack ref — so a downstream consumer reading the bundle can tell it
    MUST NOT be released (matching ``make export``'s stamped provenance).

    Red-before: at 7f7a251 BuildManifestV1 has no draft fields and PublishStage
    stamps nothing, so the published manifest is indistinguishable from a clean
    release — these keys are absent and the assertions fail.
    """
    ctx = make_ctx(tmp_path)
    ctx.publish_review_only = True
    run_prerequisites(ctx)
    summary = seed_blocking_summary(ctx)

    result = PublishStage().run(ctx, None)
    assert result.review_only is True and result.blocking is True

    manifest = read_manifest(tmp_path)
    assert manifest["review_only_draft"] is True
    assert manifest["blocking_qa_codes"] == ["GLUED_TEXT"]
    assert manifest["review_pack_ref"] == summary.review_pack_ref


def test_publish_clean_release_manifest_has_no_draft_label(tmp_path: Path) -> None:
    """A clean (non-blocking) release leaves the draft label at its defaults.

    Red-before: N/A for the false/empty assertions — the fields did not exist at
    7f7a251 so ``review_only_draft`` would raise KeyError; with the fix the clean
    release is explicitly unlabeled (False / empty).
    """
    ctx = make_ctx(tmp_path)
    run_prerequisites(ctx)

    result = PublishStage().run(ctx, None)
    assert result.blocking is False

    manifest = read_manifest(tmp_path)
    assert manifest["review_only_draft"] is False
    assert manifest["blocking_qa_codes"] == []


def test_publish_draft_manifest_agrees_with_export_provenance(tmp_path: Path) -> None:
    """The PublishStage draft and the ``make export`` draft self-describe the same way.

    PublishStage stamps ``review_only_draft`` / ``blocking_qa_codes`` /
    ``review_pack_ref`` into BuildManifestV1; ``make export``'s
    ``stamp_draft_provenance`` stamps the same fields into its manifest
    provenance. This asserts the two surfaces agree on the draft disposition
    derived from the same gate result (the core S5U-894 gap).
    """
    export_gate = _load_export_gate_module()

    ctx = make_ctx(tmp_path)
    ctx.publish_review_only = True
    run_prerequisites(ctx)
    summary = seed_blocking_summary(ctx)
    PublishStage().run(ctx, None)
    publish_manifest = read_manifest(tmp_path)

    # The export path derives provenance from the SAME gate-result shape.
    gate_result = QAGateResult(
        blocking=True,
        review_only=True,
        blocking_codes=["GLUED_TEXT"],
        review_pack_ref=summary.review_pack_ref,
    )
    provenance = export_gate.stamp_draft_provenance({}, gate_result)

    # Both surfaces flag the draft, name the same blocking codes, and point at
    # the same review pack — they agree.
    assert publish_manifest["review_only_draft"] is True
    assert provenance["review_only_draft"] == "true"
    assert provenance["blocking_qa_codes"] == ",".join(publish_manifest["blocking_qa_codes"])
    assert provenance["review_pack_ref"] == publish_manifest["review_pack_ref"]


class _PublishStageV11(PublishStage):
    """PublishStage pinned to the pre-S5U-894 version (1.1) to seed a stale event.

    Used to prove the S5U-662 invariant: a publish event cached under the OLD
    version must not be served once the label was added at v1.2 — otherwise the
    cache hit short-circuits ``run()`` and the draft label is silently absent.
    """

    @property
    def version(self) -> str:
        return "1.1"


def test_publish_version_bump_invalidates_pre_label_cache(tmp_path: Path) -> None:
    """S5U-662 / S5U-894: a v1.1-cached publish event is not served at v1.2.

    The label fields were added to ``run()``'s on-disk manifest in S5U-894. The
    PublishStage ``version`` was bumped 1.1 -> 1.2 in the same change so a publish
    event cached under v1.1 (whose manifest carries no draft label) cannot be
    served from cache — the v1.2 run misses and (re)writes the labeled manifest.

    The stale v1.1 event is seeded, then the on-disk manifest is deleted. If the
    version had NOT been bumped, the v1.2 stage would share the v1.1 cache key,
    hit the cached event, short-circuit ``run()``, and leave NO manifest on disk
    (the regression). Because it WAS bumped, the v1.2 run misses and the labeled
    manifest is present.

    Red-before: revert the 1.1 -> 1.2 bump (pin version to "1.1") and this fails —
    the second execute_stage serves the v1.1 cache and the manifest is missing.
    """
    ctx = make_ctx(tmp_path)
    ctx.publish_review_only = True
    run_prerequisites(ctx)
    seed_blocking_summary(ctx)

    # Seed a completed publish event under the OLD version (1.1).
    stale = execute_stage(_PublishStageV11(), ctx)
    assert stale.success and not stale.cached

    manifest_path = tmp_path / "artifacts" / "walking_skeleton" / "release" / "ru" / "manifest.json"
    manifest_path.unlink()  # drop the on-disk manifest the v1.1 run wrote

    # Run the real stage (v1.2). The version bump means a different cache key,
    # so the v1.1 event is NOT served — run() re-executes and writes the label.
    result = execute_stage(PublishStage(), ctx)
    assert result.success
    assert result.cached is False, "v1.2 must miss the v1.1-cached event (version bump)"
    assert json.loads(manifest_path.read_text())["review_only_draft"] is True
