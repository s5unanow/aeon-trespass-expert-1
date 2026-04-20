"""Regression tests for scripts/bootstrap_{extended,golden}_fixtures.py.

Both scripts pin the same two NEVER-rule invariants that originally regressed
in S5U-590 (extended) and remained in the golden script until S5U-665:

1. PDF artifact writes must go through ``atomic_write_bytes`` rather than
   PyMuPDF's direct ``doc.save(<canonical_path>)`` — an interrupted run would
   otherwise leave a truncated file at the canonical fixture path.
2. Diagnostic output must use ``logging`` rather than ``print()`` per
   ``.claude/rules/pipeline.md``.

Extended-fixtures row (``bootstrap_extended_fixtures``): red-before established
by S5U-645 commit ``4d9e9b6`` (tests failing) → ``ab3d15f`` (production fix
flips all four green). Merged as PR #281, merge SHA ``1a7d832``.

Golden-fixtures row (``bootstrap_golden_fixtures``): red-before established
at branch base SHA ``b115d25`` (main HEAD at branch-off), where
``scripts/bootstrap_golden_fixtures.py`` still contained 6x ``doc.save(...)``
calls and 2x ``print(...)`` calls (see S5U-665 issue body for the grep
listing). All six tests in this module fail against ``b115d25`` and pass
against the S5U-665 production fix (the same commit that introduces this
parametrization).
"""

from __future__ import annotations

import importlib.util
import logging
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class BootstrapCase:
    """Spec for one bootstrap script under test."""

    module_name: str
    script_path: Path
    # Ordered list of canonical PDF filenames produced by main().
    expected_pdfs: tuple[str, ...]
    # Relative dirs (under FIXTURES_ROOT) that main() expects to exist before
    # the per-fixture builders run — used for e.g. shared icon files that live
    # outside of main()'s ``_ensure_dirs`` loop. Empty tuple when main() creates
    # every path it needs.
    pre_seed_dirs: tuple[str, ...] = ()


CASES: list[BootstrapCase] = [
    BootstrapCase(
        module_name="bootstrap_extended_fixtures",
        script_path=REPO / "scripts" / "bootstrap_extended_fixtures.py",
        expected_pdfs=(
            "chapter_opener.pdf",
            "confidence_bands.pdf",
            "vector_heavy.pdf",
        ),
    ),
    BootstrapCase(
        module_name="bootstrap_golden_fixtures",
        script_path=REPO / "scripts" / "bootstrap_golden_fixtures.py",
        expected_pdfs=(
            "figure_caption.pdf",
            "furniture_repetition.pdf",
            "hard_route.pdf",
            "icon_dense.pdf",
            "multi_column.pdf",
            "table_callout.pdf",
        ),
        # main() writes the shared icon to walking_skeleton/source before the
        # per-fixture builders run; that dir is seeded elsewhere in the real
        # fixtures tree and is not created by this script.
        pre_seed_dirs=("walking_skeleton/source",),
    ),
]


def _seed_fixtures_root(tmp_path: Path, case: BootstrapCase) -> None:
    """Create any case-specific pre-seeded directories under ``tmp_path``."""
    for rel in case.pre_seed_dirs:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)


IDS = [c.module_name for c in CASES]


@pytest.fixture()
def bootstrap_module(request: pytest.FixtureRequest) -> Iterator[ModuleType]:
    """Import the target bootstrap script as a module for the current case."""
    case: BootstrapCase = request.param
    spec = importlib.util.spec_from_file_location(case.module_name, case.script_path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[case.module_name] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop(case.module_name, None)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_script_source_contains_no_print_calls(case: BootstrapCase) -> None:
    """Module source must not call ``print(`` for diagnostics (NEVER-rule)."""
    source = case.script_path.read_text(encoding="utf-8")
    assert "print(" not in source, (
        f"{case.script_path.relative_to(REPO)} must not use print() — "
        "use logging per .claude/rules/pipeline.md"
    )


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_script_source_does_not_call_doc_save_directly(case: BootstrapCase) -> None:
    """PDF writes must not go through raw ``doc.save(...)`` (NEVER-rule).

    An interrupted ``doc.save`` leaves a truncated PDF at the canonical
    fixture path. The atomic helper writes to a temp sibling and renames.
    """
    source = case.script_path.read_text(encoding="utf-8")
    offenders = re.findall(r"\bdoc\.save\s*\(", source)
    assert offenders == [], (
        f"{case.script_path.relative_to(REPO)} must route PDF writes through "
        "atr_pipeline.store.atomic_write — direct doc.save() is non-atomic"
    )


@pytest.mark.parametrize(
    "bootstrap_module,case",
    [(c, c) for c in CASES],
    ids=IDS,
    indirect=["bootstrap_module"],
)
def test_main_routes_all_pdf_writes_through_atomic_write(
    bootstrap_module: ModuleType, case: BootstrapCase, tmp_path: Path
) -> None:
    """Running ``main()`` must invoke ``atomic_write_bytes`` for every canonical PDF."""
    calls: list[tuple[Path, int]] = []

    def _record(path: Path, data: bytes) -> None:
        # Still perform the write so follow-on code (doc.close) is unaffected.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        calls.append((path, len(data)))

    _seed_fixtures_root(tmp_path, case)
    with (
        patch.object(bootstrap_module, "FIXTURES_ROOT", tmp_path),
        patch.object(bootstrap_module, "atomic_write_bytes", _record),
    ):
        bootstrap_module.main()

    expected_count = len(case.expected_pdfs)
    assert len(calls) == expected_count, (
        f"expected {expected_count} atomic_write_bytes calls, got {len(calls)}: {calls}"
    )
    names = sorted(p.name for p, _ in calls)
    assert names == list(case.expected_pdfs)
    for path, size in calls:
        assert size > 0, f"empty PDF payload for {path}"
        assert path.read_bytes().startswith(b"%PDF"), f"not a PDF: {path}"


@pytest.mark.parametrize(
    "bootstrap_module,case",
    [(c, c) for c in CASES],
    ids=IDS,
    indirect=["bootstrap_module"],
)
def test_main_emits_diagnostics_via_logging(
    bootstrap_module: ModuleType,
    case: BootstrapCase,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Status output must flow through the module logger, not print()."""
    _seed_fixtures_root(tmp_path, case)
    with (
        patch.object(bootstrap_module, "FIXTURES_ROOT", tmp_path),
        caplog.at_level(logging.INFO, logger=case.module_name),
    ):
        bootstrap_module.main()

    messages = [rec.getMessage() for rec in caplog.records]
    # Each fixture emits a "generated <stem>" line; a final Done marker is emitted too.
    for pdf_name in case.expected_pdfs:
        stem = pdf_name[: -len(".pdf")]
        assert any(f"generated {stem}" in m for m in messages), (
            f"missing 'generated {stem}' log line; got: {messages}"
        )
    assert any("Done" in m for m in messages)
