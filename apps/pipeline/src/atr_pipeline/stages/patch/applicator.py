"""Patch applicator — apply PatchSetV1 operations to artifact dicts.

Supports JSON Pointer (RFC 6901) paths with replace, insert, and delete
operations.  The modified artifact dict is returned; the original is
not mutated.
"""

from __future__ import annotations

import copy
from typing import Any

from atr_schemas.patch_set_v1 import PatchOperation, PatchSetV1


class PatchError(Exception):
    """Raised when a patch operation cannot be applied."""


def apply_patches(
    artifact: dict[str, Any],
    patch_set: PatchSetV1,
) -> dict[str, Any]:
    """Apply all operations in *patch_set* to a deep copy of *artifact*.

    Returns the patched artifact dict.  Raises :class:`PatchError` on
    invalid paths or unsupported operations.
    """
    result = copy.deepcopy(artifact)

    for idx, op in enumerate(patch_set.operations):
        try:
            _apply_one(result, op)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            msg = f"Patch {patch_set.patch_id} operation {idx} ({op.op} {op.path}) failed: {exc}"
            raise PatchError(msg) from exc

    return result


# ── JSON Pointer helpers (RFC 6901) ───────────────────────────────────


def _parse_pointer(pointer: str) -> list[str]:
    """Parse a JSON Pointer string into a list of unescaped tokens.

    >>> _parse_pointer("/blocks/0/children/1/text")
    ['blocks', '0', 'children', '1', 'text']
    """
    if not pointer:
        return []
    if not pointer.startswith("/"):
        msg = f"JSON Pointer must start with '/': {pointer!r}"
        raise PatchError(msg)
    parts = pointer.split("/")[1:]  # skip empty first element
    return [p.replace("~1", "/").replace("~0", "~") for p in parts]


def _resolve(
    data: Any,
    tokens: list[str],
) -> tuple[Any, str]:
    """Walk *data* following *tokens* and return (parent, final_key).

    For a path like ``/blocks/0/text``, returns the container at
    ``data["blocks"][0]`` and the key ``"text"``.
    """
    if not tokens:
        msg = "Cannot resolve empty pointer for mutation"
        raise PatchError(msg)

    current = data
    for token in tokens[:-1]:
        current = _get(current, token)

    return current, tokens[-1]


def _get(container: Any, key: str) -> Any:
    """Index into a dict or list by string key."""
    if isinstance(container, list):
        return container[int(key)]
    return container[key]


# ── Operation dispatch ────────────────────────────────────────────────


def _apply_one(data: dict[str, Any], op: PatchOperation) -> None:
    """Apply a single patch operation to *data* in-place."""
    if op.op == "replace":
        _op_replace(data, op)
    elif op.op == "insert":
        _op_insert(data, op)
    elif op.op == "delete":
        _op_delete(data, op)
    else:
        msg = f"Unsupported patch operation: {op.op!r}"
        raise PatchError(msg)


def _op_replace(data: dict[str, Any], op: PatchOperation) -> None:
    tokens = _parse_pointer(op.path)
    parent, key = _resolve(data, tokens)
    if isinstance(parent, list):
        parent[int(key)] = op.value
    else:
        parent[key] = op.value


def _op_insert(data: dict[str, Any], op: PatchOperation) -> None:
    tokens = _parse_pointer(op.path)
    parent, key = _resolve(data, tokens)
    if not isinstance(parent, list):
        msg = f"Insert requires an array target, got {type(parent).__name__}"
        raise PatchError(msg)
    idx = int(key)
    parent.insert(idx, op.value)


def _op_delete(data: dict[str, Any], op: PatchOperation) -> None:
    tokens = _parse_pointer(op.path)
    parent, key = _resolve(data, tokens)
    if isinstance(parent, list):
        del parent[int(key)]
    elif isinstance(parent, dict):
        del parent[key]
    else:
        msg = f"Delete requires a dict or list target, got {type(parent).__name__}"
        raise PatchError(msg)
