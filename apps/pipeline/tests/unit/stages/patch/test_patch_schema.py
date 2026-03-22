"""Tests for extended PatchSetV1 schema: target kind, scope, provenance."""

from __future__ import annotations

from datetime import UTC, datetime

from atr_schemas.enums import PatchScope, PatchTargetKind
from atr_schemas.patch_set_v1 import PatchOperation, PatchProvenance, PatchSetV1

# ── PatchTargetKind ───────────────────────────────────────────────────


class TestPatchTargetKind:
    """PatchSetV1.target_kind categorizes the artifact being patched."""

    def test_target_kind_page_ir(self) -> None:
        ps = PatchSetV1(patch_id="t1", target_kind=PatchTargetKind.PAGE_IR)
        assert ps.target_kind == PatchTargetKind.PAGE_IR

    def test_target_kind_resolved_page(self) -> None:
        ps = PatchSetV1(patch_id="t2", target_kind=PatchTargetKind.RESOLVED_PAGE)
        assert ps.target_kind == PatchTargetKind.RESOLVED_PAGE

    def test_target_kind_optional_default_none(self) -> None:
        ps = PatchSetV1(patch_id="t3")
        assert ps.target_kind is None

    def test_all_target_kinds_valid(self) -> None:
        for kind in PatchTargetKind:
            ps = PatchSetV1(patch_id=f"t-{kind}", target_kind=kind)
            assert ps.target_kind == kind


# ── PatchScope on operations ──────────────────────────────────────────


class TestPatchScope:
    """PatchOperation.scope classifies what the operation corrects."""

    def test_scope_text(self) -> None:
        op = PatchOperation(op="replace", path="/blocks/0/text", scope=PatchScope.TEXT)
        assert op.scope == PatchScope.TEXT

    def test_scope_reading_order(self) -> None:
        op = PatchOperation(
            op="replace",
            path="/reading_order",
            value=["b1", "b2"],
            scope=PatchScope.READING_ORDER,
        )
        assert op.scope == PatchScope.READING_ORDER

    def test_scope_optional_default_none(self) -> None:
        op = PatchOperation(op="replace", path="/x")
        assert op.scope is None

    def test_all_scopes_valid(self) -> None:
        for scope in PatchScope:
            op = PatchOperation(op="replace", path="/x", scope=scope)
            assert op.scope == scope

    def test_scope_asset_link(self) -> None:
        op = PatchOperation(
            op="replace",
            path="/blocks/0/asset_id",
            value="fig_001",
            scope=PatchScope.ASSET_LINK,
        )
        assert op.scope == PatchScope.ASSET_LINK

    def test_scope_region_assignment(self) -> None:
        op = PatchOperation(
            op="replace",
            path="/blocks/0/region_id",
            value="r002",
            scope=PatchScope.REGION_ASSIGNMENT,
        )
        assert op.scope == PatchScope.REGION_ASSIGNMENT

    def test_scope_symbol_resolution(self) -> None:
        op = PatchOperation(
            op="replace",
            path="/symbol_refs/0/symbol_id",
            value="icon_shield",
            scope=PatchScope.SYMBOL_RESOLUTION,
        )
        assert op.scope == PatchScope.SYMBOL_RESOLUTION


# ── PatchProvenance ───────────────────────────────────────────────────


class TestPatchProvenance:
    """PatchProvenance tracks who/what created the patch and its impact."""

    def test_basic_provenance(self) -> None:
        prov = PatchProvenance(
            author="reviewer@example.com",
            source_confidence=0.45,
            expected_confidence_delta=0.20,
        )
        assert prov.author == "reviewer@example.com"
        assert prov.source_confidence == 0.45
        assert prov.expected_confidence_delta == 0.20

    def test_provenance_with_timestamp(self) -> None:
        ts = datetime(2026, 3, 22, tzinfo=UTC)
        prov = PatchProvenance(author="agent", created_at=ts)
        assert prov.created_at == ts

    def test_provenance_all_optional(self) -> None:
        prov = PatchProvenance()
        assert prov.author == ""
        assert prov.created_at is None
        assert prov.source_confidence is None
        assert prov.expected_confidence_delta is None

    def test_provenance_on_patch_set(self) -> None:
        ps = PatchSetV1(
            patch_id="prov-1",
            target_kind=PatchTargetKind.PAGE_IR,
            provenance=PatchProvenance(
                author="qa-bot",
                source_confidence=0.35,
                expected_confidence_delta=0.30,
            ),
        )
        assert ps.provenance is not None
        assert ps.provenance.author == "qa-bot"
        assert ps.provenance.source_confidence == 0.35

    def test_provenance_optional_on_patch_set(self) -> None:
        ps = PatchSetV1(patch_id="no-prov")
        assert ps.provenance is None


# ── Full round-trip ───────────────────────────────────────────────────


class TestPatchSetRoundTrip:
    """Full PatchSetV1 with all new fields serializes correctly."""

    def test_full_patch_set_roundtrip(self) -> None:
        ps = PatchSetV1(
            patch_id="full-1",
            target_artifact_ref="doc/page_ir.v1.en/page/p0001/abc123.json",
            target_kind=PatchTargetKind.PAGE_IR,
            operations=[
                PatchOperation(
                    op="replace",
                    path="/blocks/0/children/1/symbol_id",
                    value="icon_action",
                    scope=PatchScope.SYMBOL_RESOLUTION,
                ),
                PatchOperation(
                    op="replace",
                    path="/reading_order",
                    value=["p0001.b002", "p0001.b001", "p0001.b003"],
                    scope=PatchScope.READING_ORDER,
                ),
            ],
            reason="Fix icon misidentification and reading order",
            author="reviewer",
            provenance=PatchProvenance(
                author="reviewer",
                source_confidence=0.52,
                expected_confidence_delta=0.25,
            ),
        )
        data = ps.model_dump(mode="json")
        restored = PatchSetV1.model_validate(data)
        assert restored.target_kind == PatchTargetKind.PAGE_IR
        assert restored.operations[0].scope == PatchScope.SYMBOL_RESOLUTION
        assert restored.operations[1].scope == PatchScope.READING_ORDER
        assert restored.provenance is not None
        assert restored.provenance.source_confidence == 0.52

    def test_backward_compatible_minimal(self) -> None:
        """Old-style patch (no target_kind/scope/provenance) still works."""
        data = {
            "schema_version": "patch_set.v1",
            "patch_id": "old-style",
            "target_artifact_ref": "some/path.json",
            "operations": [
                {"op": "replace", "path": "/blocks/0/text", "value": "fixed"},
            ],
            "reason": "typo fix",
            "author": "human",
        }
        ps = PatchSetV1.model_validate(data)
        assert ps.target_kind is None
        assert ps.operations[0].scope is None
        assert ps.provenance is None
