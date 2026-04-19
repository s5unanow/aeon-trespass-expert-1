"""Regression tests for scripts/bootstrap_extended_fixtures.py (S5U-645).

Pins the two NEVER-rule invariants that originally regressed in S5U-590:

1. PDF artifact writes must go through ``atomic_write_bytes`` rather than
   PyMuPDF's direct ``doc.save(<canonical_path>)`` — an interrupted run would
   otherwise leave a truncated file at the canonical fixture path.
2. Diagnostic output must use ``logging`` rather than ``print()`` per
   ``.claude/rules/pipeline.md``.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "bootstrap_extended_fixtures.py"


@pytest.fixture()
def bootstrap_module() -> Iterator[ModuleType]:
    """Import scripts/bootstrap_extended_fixtures.py as a module."""
    spec = importlib.util.spec_from_file_location("bootstrap_extended_fixtures", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bootstrap_extended_fixtures"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("bootstrap_extended_fixtures", None)


def test_script_source_contains_no_print_calls() -> None:
    """Module source must not call ``print(`` for diagnostics (NEVER-rule)."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    # Strip comments and docstrings is overkill — require no token ``print(``
    # anywhere, since the file has no legitimate need for it.
    assert "print(" not in source, (
        "scripts/bootstrap_extended_fixtures.py must not use print() — "
        "use logging per .claude/rules/pipeline.md"
    )


def test_script_source_does_not_call_doc_save_directly() -> None:
    """PDF writes must not go through raw ``doc.save(...)`` (NEVER-rule).

    An interrupted ``doc.save`` leaves a truncated PDF at the canonical
    fixture path. The atomic helper writes to a temp sibling and renames.
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    # Match any ``<something>.save(`` on the PyMuPDF document, not the
    # atomic helper's internal usage.
    offenders = re.findall(r"\bdoc\.save\s*\(", source)
    assert offenders == [], (
        "scripts/bootstrap_extended_fixtures.py must route PDF writes through "
        "atr_pipeline.store.atomic_write — direct doc.save() is non-atomic"
    )


def test_main_routes_all_pdf_writes_through_atomic_write(
    bootstrap_module: ModuleType, tmp_path: Path
) -> None:
    """Running ``main()`` must invoke ``atomic_write_bytes`` exactly 3 times.

    Three fixtures are generated: vector_heavy, chapter_opener, and
    confidence_bands. Each must land through the atomic helper.
    """
    calls: list[tuple[Path, int]] = []

    def _record(path: Path, data: bytes) -> None:
        # Still perform the write so follow-on code (doc.close) is unaffected.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        calls.append((path, len(data)))

    # Redirect the fixtures root into tmp_path so the test is hermetic.
    with (
        patch.object(bootstrap_module, "FIXTURES_ROOT", tmp_path),
        patch.object(bootstrap_module, "atomic_write_bytes", _record),
    ):
        bootstrap_module.main()

    assert len(calls) == 3, (
        f"expected 3 atomic_write_bytes calls (one per fixture), got {len(calls)}: {calls}"
    )
    names = sorted(p.name for p, _ in calls)
    assert names == [
        "chapter_opener.pdf",
        "confidence_bands.pdf",
        "vector_heavy.pdf",
    ]
    # All payloads should be non-empty, valid PDF bytes start with %PDF.
    for path, size in calls:
        assert size > 0, f"empty PDF payload for {path}"
        assert path.read_bytes().startswith(b"%PDF"), f"not a PDF: {path}"


def test_main_emits_diagnostics_via_logging(
    bootstrap_module: ModuleType, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Status output must flow through the module logger, not print()."""
    with (
        patch.object(bootstrap_module, "FIXTURES_ROOT", tmp_path),
        caplog.at_level(logging.INFO, logger="bootstrap_extended_fixtures"),
    ):
        bootstrap_module.main()

    messages = [rec.getMessage() for rec in caplog.records]
    # Four info lines expected: 3x "generated <name>" + final Done marker.
    assert any("generated vector_heavy" in m for m in messages)
    assert any("generated chapter_opener" in m for m in messages)
    assert any("generated confidence_bands" in m for m in messages)
    assert any("Done" in m for m in messages)
