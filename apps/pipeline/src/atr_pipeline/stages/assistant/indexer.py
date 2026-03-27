"""FTS5 index builder — builds a read-only SQLite index from RuleChunkV1 artifacts."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from atr_schemas.rule_chunk_v1 import RuleChunkV1

_CHUNKS_TABLE = """\
CREATE TABLE IF NOT EXISTS chunks (
    rule_chunk_id   TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    edition         TEXT NOT NULL,
    page_id         TEXT NOT NULL,
    source_page_number INTEGER NOT NULL,
    section_path    TEXT NOT NULL DEFAULT '[]',
    block_ids       TEXT NOT NULL DEFAULT '[]',
    canonical_anchor_id TEXT NOT NULL,
    language        TEXT NOT NULL,
    text            TEXT NOT NULL,
    normalized_text TEXT NOT NULL DEFAULT '',
    glossary_json   TEXT NOT NULL DEFAULT '[]',
    symbol_ids      TEXT NOT NULL DEFAULT '[]',
    deep_link       TEXT NOT NULL DEFAULT ''
)
"""

_FTS_TABLE = """\
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    rule_chunk_id UNINDEXED,
    normalized_text,
    section_text,
    glossary_text,
    symbol_text,
    content=chunks,
    content_rowid=rowid,
    tokenize='unicode61'
)
"""

_FTS_INSERT = """\
INSERT INTO chunks_fts(
    rowid, rule_chunk_id, normalized_text,
    section_text, glossary_text, symbol_text
)
SELECT rowid, rule_chunk_id, normalized_text,
       json_extract(section_path, '$') AS section_text,
       glossary_json AS glossary_text,
       symbol_ids AS symbol_text
FROM chunks
"""


def build_index(chunks: list[RuleChunkV1], db_path: Path) -> Path:
    """Build a read-only FTS5 SQLite index from rule chunks.

    Creates the database at *db_path*, populates the ``chunks`` table
    and the ``chunks_fts`` FTS5 virtual table, then returns *db_path*.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        _create_tables(conn)
        _insert_chunks(conn, chunks)
        _populate_fts(conn)
        conn.execute("PRAGMA optimize")
        conn.commit()
    finally:
        conn.close()

    return db_path


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(_CHUNKS_TABLE)
    conn.execute(_FTS_TABLE)


def _insert_chunks(conn: sqlite3.Connection, chunks: list[RuleChunkV1]) -> None:
    for chunk in chunks:
        glossary_text = _glossary_to_searchable(chunk)
        conn.execute(
            """INSERT OR REPLACE INTO chunks
               (rule_chunk_id, document_id, edition, page_id,
                source_page_number, section_path, block_ids,
                canonical_anchor_id, language, text, normalized_text,
                glossary_json, symbol_ids, deep_link)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.rule_chunk_id,
                chunk.document_id,
                chunk.edition,
                chunk.page_id,
                chunk.source_page_number,
                json.dumps(chunk.section_path, ensure_ascii=False),
                json.dumps(chunk.block_ids, ensure_ascii=False),
                chunk.canonical_anchor_id,
                chunk.language.value,
                chunk.text,
                chunk.normalized_text,
                glossary_text,
                json.dumps(chunk.symbol_ids, ensure_ascii=False),
                chunk.deep_link,
            ),
        )


def _glossary_to_searchable(chunk: RuleChunkV1) -> str:
    """Flatten glossary concepts into a searchable text blob.

    Concatenates concept_id and surface_form so FTS can match on
    glossary terms directly.
    """
    parts: list[str] = []
    for gc in chunk.glossary_concepts:
        parts.append(gc.concept_id)
        if gc.surface_form:
            parts.append(gc.surface_form)
    return " ".join(parts) if parts else ""


def _populate_fts(conn: sqlite3.Connection) -> None:
    """Populate the FTS5 content table from the chunks table."""
    conn.execute(_FTS_INSERT)


def query_index(db_path: Path, query: str, *, limit: int = 10) -> list[dict[str, object]]:
    """Run a simple FTS5 query and return matching chunks.

    Returns a list of dicts with chunk metadata, ordered by FTS rank.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT c.rule_chunk_id, c.document_id, c.edition, c.page_id,
                      c.source_page_number, c.canonical_anchor_id, c.language,
                      c.text, c.deep_link, c.section_path, c.glossary_json,
                      c.symbol_ids
               FROM chunks_fts f
               JOIN chunks c ON c.rowid = f.rowid
               WHERE chunks_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
