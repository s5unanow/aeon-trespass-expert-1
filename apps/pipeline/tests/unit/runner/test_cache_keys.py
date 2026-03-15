"""Tests for deterministic cache key computation."""

from atr_pipeline.runner.cache_keys import build_cache_key


def test_cache_key_is_deterministic() -> None:
    """Same inputs produce the same cache key."""
    key1 = build_cache_key(
        stage_name="extract_native",
        stage_version="1.0",
        schema_version="native_page.v1",
        config_hash="abc123",
        input_hashes=["hash1", "hash2"],
    )
    key2 = build_cache_key(
        stage_name="extract_native",
        stage_version="1.0",
        schema_version="native_page.v1",
        config_hash="abc123",
        input_hashes=["hash1", "hash2"],
    )
    assert key1 == key2


def test_cache_key_changes_on_different_input() -> None:
    """Different inputs produce different cache keys."""
    key1 = build_cache_key(
        stage_name="extract_native",
        stage_version="1.0",
        schema_version="native_page.v1",
        config_hash="abc123",
        input_hashes=["hash1"],
    )
    key2 = build_cache_key(
        stage_name="extract_native",
        stage_version="1.0",
        schema_version="native_page.v1",
        config_hash="abc123",
        input_hashes=["hash_different"],
    )
    assert key1 != key2


def test_cache_key_input_order_independent() -> None:
    """Input hashes are sorted, so order doesn't matter."""
    key1 = build_cache_key(
        stage_name="s", stage_version="1", schema_version="v1",
        config_hash="c", input_hashes=["a", "b"],
    )
    key2 = build_cache_key(
        stage_name="s", stage_version="1", schema_version="v1",
        config_hash="c", input_hashes=["b", "a"],
    )
    assert key1 == key2


def test_cache_key_with_patches() -> None:
    """Patches participate in the key."""
    key_no_patch = build_cache_key(
        stage_name="s", stage_version="1", schema_version="v1",
        config_hash="c", input_hashes=["h1"],
    )
    key_with_patch = build_cache_key(
        stage_name="s", stage_version="1", schema_version="v1",
        config_hash="c", input_hashes=["h1"], patch_hashes=["p1"],
    )
    assert key_no_patch != key_with_patch


def test_cache_key_is_12_hex_chars() -> None:
    """Cache key is a 12-character hex string."""
    key = build_cache_key(
        stage_name="test", stage_version="1", schema_version="v1",
        config_hash="c", input_hashes=["h"],
    )
    assert len(key) == 12
    assert all(c in "0123456789abcdef" for c in key)
