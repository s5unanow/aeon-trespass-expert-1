"""Tests for the FTS5 index builder module."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from atr_pipeline.stages.assistant.indexer import build_index, query_index
from atr_schemas.enums import LanguageCode
from atr_schemas.rule_chunk_v1 import GlossaryConcept, RuleChunkV1


def _make_chunk(
    chunk_id: str = "doc.chunk.0001.abc12345.en",
    text: str = "Move your titan two spaces forward.",
    page_id: str = "p0001",
    page_number: int = 1,
    section_path: list[str] | None = None,
    glossary: list[GlossaryConcept] | None = None,
    symbol_ids: list[str] | None = None,
) -> RuleChunkV1:
    return RuleChunkV1(
        rule_chunk_id=chunk_id,
        document_id="test_doc",
        edition="en",
        page_id=page_id,
        source_page_number=page_number,
        section_path=section_path or [],
        block_ids=["p0001.b001"],
        canonical_anchor_id="chunk.0001.abc12345",
        language=LanguageCode.EN,
        text=text,
        normalized_text=text.lower(),
        glossary_concepts=glossary or [],
        symbol_ids=symbol_ids or [],
        deep_link=f"/documents/test_doc/en/{page_id}#anchor=chunk.0001.abc12345",
    )


def test_build_index_creates_db(tmp_path: Path) -> None:
    """build_index creates a SQLite database at the given path."""
    db_path = tmp_path / "test.sqlite"
    chunks = [_make_chunk()]
    build_index(chunks, db_path)
    assert db_path.exists()


def test_build_index_stores_all_chunks(tmp_path: Path) -> None:
    """All chunks are stored in the chunks table."""
    db_path = tmp_path / "test.sqlite"
    chunks = [
        _make_chunk(chunk_id="doc.chunk.0001.a.en", text="First rule."),
        _make_chunk(chunk_id="doc.chunk.0002.b.en", text="Second rule."),
        _make_chunk(chunk_id="doc.chunk.0003.c.en", text="Third rule."),
    ]
    build_index(chunks, db_path)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    assert count == 3


def test_fts_query_matches_text(tmp_path: Path) -> None:
    """FTS5 query matches on normalized text content."""
    db_path = tmp_path / "test.sqlite"
    chunks = [
        _make_chunk(chunk_id="doc.c1.en", text="Move your titan forward."),
        _make_chunk(chunk_id="doc.c2.en", text="Draw three cards from the deck."),
    ]
    build_index(chunks, db_path)

    results = query_index(db_path, "titan")
    assert len(results) == 1
    assert results[0]["rule_chunk_id"] == "doc.c1.en"


def test_fts_query_matches_glossary(tmp_path: Path) -> None:
    """FTS5 query matches on glossary concept text."""
    db_path = tmp_path / "test.sqlite"
    chunks = [
        _make_chunk(
            chunk_id="doc.c1.en",
            text="Use the focus action.",
            glossary=[GlossaryConcept(concept_id="c_focus", surface_form="Focus")],
        ),
        _make_chunk(chunk_id="doc.c2.en", text="Discard a card."),
    ]
    build_index(chunks, db_path)

    results = query_index(db_path, "c_focus")
    assert len(results) == 1
    assert results[0]["rule_chunk_id"] == "doc.c1.en"


def test_fts_query_matches_symbol(tmp_path: Path) -> None:
    """FTS5 query matches on symbol IDs."""
    db_path = tmp_path / "test.sqlite"
    chunks = [
        _make_chunk(
            chunk_id="doc.c1.en",
            text="Roll a die.",
            symbol_ids=["dice_d6"],
        ),
        _make_chunk(chunk_id="doc.c2.en", text="Move forward."),
    ]
    build_index(chunks, db_path)

    results = query_index(db_path, "dice_d6")
    assert len(results) == 1
    assert results[0]["rule_chunk_id"] == "doc.c1.en"


def test_fts_query_returns_metadata(tmp_path: Path) -> None:
    """Query results include all expected metadata fields."""
    db_path = tmp_path / "test.sqlite"
    chunks = [_make_chunk()]
    build_index(chunks, db_path)

    results = query_index(db_path, "titan")
    assert len(results) == 1
    row = results[0]
    assert row["document_id"] == "test_doc"
    assert row["edition"] == "en"
    assert row["page_id"] == "p0001"
    assert row["source_page_number"] == 1
    assert isinstance(row["deep_link"], str)
    assert row["deep_link"].startswith("/documents/")
    assert "canonical_anchor_id" in row


def test_fts_query_respects_limit(tmp_path: Path) -> None:
    """Query limit restricts result count."""
    db_path = tmp_path / "test.sqlite"
    chunks = [
        _make_chunk(chunk_id=f"doc.c{i}.en", text=f"Rule about titans number {i}.")
        for i in range(10)
    ]
    build_index(chunks, db_path)

    results = query_index(db_path, "titans", limit=3)
    assert len(results) == 3


def test_fts_no_results_for_unmatched_query(tmp_path: Path) -> None:
    """Query returns empty list for unmatched terms."""
    db_path = tmp_path / "test.sqlite"
    chunks = [_make_chunk()]
    build_index(chunks, db_path)

    results = query_index(db_path, "nonexistent_xyz")
    assert results == []


def test_build_index_overwrites_existing(tmp_path: Path) -> None:
    """Building index twice overwrites the previous database."""
    db_path = tmp_path / "test.sqlite"
    build_index([_make_chunk(chunk_id="doc.c1.en", text="Old data.")], db_path)
    build_index([_make_chunk(chunk_id="doc.c2.en", text="New data.")], db_path)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    ids = [r[0] for r in conn.execute("SELECT rule_chunk_id FROM chunks").fetchall()]
    conn.close()
    assert count == 1
    assert ids == ["doc.c2.en"]


def test_empty_chunks_produces_empty_index(tmp_path: Path) -> None:
    """Building index with no chunks creates valid empty database."""
    db_path = tmp_path / "test.sqlite"
    build_index([], db_path)
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    assert count == 0


def test_chunk_metadata_round_trips(tmp_path: Path) -> None:
    """Section path, glossary, and symbol data survive round-trip."""
    db_path = tmp_path / "test.sqlite"
    chunks = [
        _make_chunk(
            section_path=["Chapter 1", "Movement"],
            glossary=[GlossaryConcept(concept_id="c_titan", surface_form="Titan")],
            symbol_ids=["icon_move", "icon_attack"],
        ),
    ]
    build_index(chunks, db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM chunks").fetchone()
    conn.close()

    assert '"Chapter 1"' in row["section_path"]
    assert "c_titan" in row["glossary_text"]
    assert "icon_move" in row["symbol_ids"]
