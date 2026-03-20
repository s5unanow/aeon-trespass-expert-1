"""Tests for the patch applicator utility."""

from __future__ import annotations

from typing import Any

import pytest

from atr_pipeline.stages.patch.applicator import PatchError, apply_patches
from atr_schemas.patch_set_v1 import PatchOperation, PatchSetV1


def _patch_set(ops: list[dict[str, Any]], patch_id: str = "test-1") -> PatchSetV1:
    return PatchSetV1(
        patch_id=patch_id,
        operations=[PatchOperation(**o) for o in ops],
    )


# ── Replace ───────────────────────────────────────────────────────────


def test_replace_scalar() -> None:
    artifact = {"title": "old"}
    ops = [{"op": "replace", "path": "/title", "value": "new"}]
    result = apply_patches(artifact, _patch_set(ops))
    assert result["title"] == "new"


def test_replace_nested() -> None:
    artifact = {"blocks": [{"text": "hello"}]}
    result = apply_patches(
        artifact,
        _patch_set([{"op": "replace", "path": "/blocks/0/text", "value": "world"}]),
    )
    assert result["blocks"][0]["text"] == "world"


def test_replace_array_element() -> None:
    artifact = {"items": ["a", "b", "c"]}
    result = apply_patches(
        artifact,
        _patch_set([{"op": "replace", "path": "/items/1", "value": "B"}]),
    )
    assert result["items"] == ["a", "B", "c"]


# ── Insert ────────────────────────────────────────────────────────────


def test_insert_into_array() -> None:
    artifact = {"items": ["a", "c"]}
    result = apply_patches(
        artifact,
        _patch_set([{"op": "insert", "path": "/items/1", "value": "b"}]),
    )
    assert result["items"] == ["a", "b", "c"]


def test_insert_at_end() -> None:
    artifact = {"items": ["a", "b"]}
    result = apply_patches(
        artifact,
        _patch_set([{"op": "insert", "path": "/items/2", "value": "c"}]),
    )
    assert result["items"] == ["a", "b", "c"]


def test_insert_rejects_non_array() -> None:
    artifact = {"data": {"key": "val"}}
    with pytest.raises(PatchError, match="array target"):
        apply_patches(
            artifact,
            _patch_set([{"op": "insert", "path": "/data/key", "value": "x"}]),
        )


# ── Delete ────────────────────────────────────────────────────────────


def test_delete_dict_key() -> None:
    artifact = {"a": 1, "b": 2}
    result = apply_patches(
        artifact,
        _patch_set([{"op": "delete", "path": "/b"}]),
    )
    assert result == {"a": 1}


def test_delete_array_element() -> None:
    artifact = {"items": ["a", "b", "c"]}
    result = apply_patches(
        artifact,
        _patch_set([{"op": "delete", "path": "/items/1"}]),
    )
    assert result["items"] == ["a", "c"]


# ── Multiple operations ──────────────────────────────────────────────


def test_multiple_operations() -> None:
    artifact = {"blocks": [{"text": "old"}, {"text": "keep"}]}
    result = apply_patches(
        artifact,
        _patch_set(
            [
                {"op": "replace", "path": "/blocks/0/text", "value": "new"},
                {"op": "delete", "path": "/blocks/1"},
            ]
        ),
    )
    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["text"] == "new"


# ── Original not mutated ─────────────────────────────────────────────


def test_original_not_mutated() -> None:
    artifact = {"title": "original"}
    apply_patches(artifact, _patch_set([{"op": "replace", "path": "/title", "value": "patched"}]))
    assert artifact["title"] == "original"


# ── Error handling ────────────────────────────────────────────────────


def test_invalid_pointer_no_slash() -> None:
    with pytest.raises(PatchError, match="must start with"):
        apply_patches({"x": 1}, _patch_set([{"op": "replace", "path": "x", "value": 2}]))


def test_invalid_path_missing_parent() -> None:
    """Traversing through a non-existent intermediate key should fail."""
    with pytest.raises(PatchError):
        apply_patches(
            {"a": 1},
            _patch_set([{"op": "replace", "path": "/missing/child", "value": 2}]),
        )


def test_unsupported_op() -> None:
    with pytest.raises(PatchError, match="Unsupported"):
        apply_patches({"a": 1}, _patch_set([{"op": "move", "path": "/a", "value": None}]))


# ── Escaped pointer tokens ───────────────────────────────────────────


def test_escaped_pointer_tilde() -> None:
    """RFC 6901: ~0 decodes to ~ and ~1 decodes to /."""
    artifact = {"a/b": {"c~d": "val"}}
    result = apply_patches(
        artifact,
        _patch_set([{"op": "replace", "path": "/a~1b/c~0d", "value": "new"}]),
    )
    assert result["a/b"]["c~d"] == "new"


# ── Empty patch set ──────────────────────────────────────────────────


def test_empty_operations() -> None:
    artifact = {"key": "val"}
    result = apply_patches(artifact, _patch_set([]))
    assert result == artifact
