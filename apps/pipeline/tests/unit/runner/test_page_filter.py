"""Tests for page filter parsing and application."""

from __future__ import annotations

from atr_pipeline.runner.stage_context import parse_page_filter


def test_parse_single_page() -> None:
    result = parse_page_filter("15")
    assert result == frozenset({"p0015"})


def test_parse_multiple_pages() -> None:
    result = parse_page_filter("1,3,5")
    assert result == frozenset({"p0001", "p0003", "p0005"})


def test_parse_range() -> None:
    result = parse_page_filter("2-4")
    assert result == frozenset({"p0002", "p0003", "p0004"})


def test_parse_mixed() -> None:
    result = parse_page_filter("1,3-5,8")
    assert result == frozenset({"p0001", "p0003", "p0004", "p0005", "p0008"})


def test_parse_with_spaces() -> None:
    result = parse_page_filter("1, 3 ,5")
    assert result == frozenset({"p0001", "p0003", "p0005"})


def test_parse_empty_string() -> None:
    result = parse_page_filter("")
    assert result == frozenset()
