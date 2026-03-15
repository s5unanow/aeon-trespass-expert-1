"""Deterministic cache key computation for stage outputs."""

from __future__ import annotations

from atr_pipeline.utils.hashing import sha256_str


def build_cache_key(
    *,
    stage_name: str,
    stage_version: str,
    schema_version: str,
    config_hash: str,
    input_hashes: list[str],
    patch_hashes: list[str] | None = None,
    provider_info: str = "",
) -> str:
    """Build a deterministic cache key for a stage invocation.

    The key is a short hex hash of all inputs that affect output.
    """
    parts = [
        f"stage={stage_name}",
        f"stage_v={stage_version}",
        f"schema_v={schema_version}",
        f"config={config_hash}",
        f"inputs={'|'.join(sorted(input_hashes))}",
    ]
    if patch_hashes:
        parts.append(f"patches={'|'.join(sorted(patch_hashes))}")
    if provider_info:
        parts.append(f"provider={provider_info}")

    combined = "\n".join(parts)
    return sha256_str(combined)[:12]
