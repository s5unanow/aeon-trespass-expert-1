"""Tests for scripts/check_make_doc_parity.py (S5U-690)."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "check_make_doc_parity.py"


@pytest.fixture()
def mod() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("check_make_doc_parity", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_make_doc_parity"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("check_make_doc_parity", None)


# ---------------------------------------------------------------------------
# Makefile token extraction
# ---------------------------------------------------------------------------


def _write_makefile(tmp_path: Path, body: str) -> Path:
    (tmp_path / "Makefile").write_text(body, encoding="utf-8")
    return tmp_path / "Makefile"


def test_makefile_lint_tokens_recovers_expected_stems(mod: ModuleType) -> None:
    text = (
        "lint:\n"
        "\tuv run ruff check .\n"
        "\tuv run ruff format --check .\n"
        "\tuv run mypy apps/pipeline/src\n"
        "\tuv run lint-imports\n"
        "\tuv run python scripts/check_file_length.py\n"
        "\tbash scripts/check_codegen_fresh.sh\n"
        "\tpnpm -r run lint\n"
    )
    tokens = mod.makefile_lint_tokens(text)
    # Stems of noun-sense tools. `uv`, `python`, `bash`, `pnpm` are wrapper
    # words (filtered), so the first non-wrapper stem per line is captured:
    # `ruff`, `mypy`, `lint-imports`, `check_file_length`,
    # `check_codegen_fresh`, and — for `pnpm -r run lint` — `lint` (the
    # pnpm script name). A doc summary containing "pnpm lint" substring-
    # matches the `lint` stem naturally.
    assert "ruff" in tokens
    assert "mypy" in tokens
    assert "lint-imports" in tokens
    assert "check_file_length" in tokens
    assert "check_codegen_fresh" in tokens
    assert "lint" in tokens


def test_missing_lint_target_fails_closed(mod: ModuleType) -> None:
    text = "format:\n\tuv run ruff format .\n"
    with pytest.raises(RuntimeError, match="lint"):
        mod.makefile_lint_tokens(text)


def test_empty_lint_target_fails_closed(mod: ModuleType) -> None:
    # Has the target header but no command lines — must not silently return
    # zero tokens (that would fail-open the downstream doc-parity check).
    text = "lint:\n"
    with pytest.raises(RuntimeError):
        mod.makefile_lint_tokens(text)


# ---------------------------------------------------------------------------
# Alias-tolerant doc matching
# ---------------------------------------------------------------------------


def test_alias_substring_match(mod: ModuleType) -> None:
    # The alias table maps `validate_fixture_manifest` -> `fixture-manifest`;
    # a doc line using the alias must satisfy the check for the stem.
    assert mod.stem_is_documented(
        "validate_fixture_manifest",
        "ruff check + fixture-manifest + pnpm lint",
    )


def test_alias_miss_detects_drift(mod: ModuleType) -> None:
    # No alias or stem substring present -> drift.
    assert not mod.stem_is_documented(
        "validate_fixture_manifest",
        "ruff check + pnpm lint",
    )


def test_codegen_alias_match(mod: ModuleType) -> None:
    # `check_codegen_fresh` -> alias `codegen` is enough.
    assert mod.stem_is_documented(
        "check_codegen_fresh",
        "ruff check + codegen freshness + pnpm lint",
    )


# ---------------------------------------------------------------------------
# CLAUDE.md summary extraction
# ---------------------------------------------------------------------------


def test_extract_claude_summary_captures_comment(mod: ModuleType) -> None:
    text = (
        "## Commands\n"
        "```bash\n"
        "make bootstrap        # Install all deps\n"
        "make lint             # ruff check + mypy + pnpm lint\n"
        "```\n"
    )
    summary = mod.extract_claude_summary(text)
    assert summary == "ruff check + mypy + pnpm lint"


def test_extract_claude_summary_missing_fails_closed(mod: ModuleType) -> None:
    with pytest.raises(RuntimeError):
        mod.extract_claude_summary("## Commands\nmake test\n")


def test_extract_claude_summary_empty_comment_fails_closed(mod: ModuleType) -> None:
    # A `make lint #` line with no body must fail closed — an empty summary
    # is semantically equivalent to undocumented and would silently pass
    # every drift check.
    with pytest.raises(RuntimeError):
        mod.extract_claude_summary("make lint             # \n")


# ---------------------------------------------------------------------------
# End-to-end audit
# ---------------------------------------------------------------------------


def _write_template(tmp_path: Path, summary: str) -> None:
    rel = Path("docs/EXTRACTION_TICKET_TEMPLATE.md")
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"### Quality Gates\n\n- [ ] `make lint` passes ({summary})\n",
        encoding="utf-8",
    )


def _write_all(
    tmp_path: Path, makefile_body: str, claude_summary: str, template_summary: str
) -> None:
    _write_makefile(tmp_path, makefile_body)
    (tmp_path / "CLAUDE.md").write_text(
        f"## Commands\n```bash\nmake lint             # {claude_summary}\n```\n",
        encoding="utf-8",
    )
    _write_template(tmp_path, template_summary)


def test_audit_happy_path(mod: ModuleType, tmp_path: Path) -> None:
    _write_all(
        tmp_path,
        makefile_body=(
            "lint:\n"
            "\tuv run ruff check .\n"
            "\tuv run python scripts/validate_fixture_manifest.py\n"
            "\tpnpm -r run lint\n"
        ),
        claude_summary="ruff check + fixture-manifest + pnpm lint",
        template_summary="ruff check + fixture-manifest + pnpm lint",
    )
    assert mod.audit(tmp_path) == []


def test_audit_detects_missing_token_in_claude(mod: ModuleType, tmp_path: Path) -> None:
    # The original S5U-690 drift: Makefile runs `validate_fixture_manifest`
    # but CLAUDE.md omits it.
    _write_all(
        tmp_path,
        makefile_body=(
            "lint:\n"
            "\tuv run ruff check .\n"
            "\tuv run python scripts/validate_fixture_manifest.py\n"
            "\tpnpm -r run lint\n"
        ),
        claude_summary="ruff check + pnpm lint",  # missing fixture-manifest
        template_summary="ruff check + fixture-manifest + pnpm lint",
    )
    drift = mod.audit(tmp_path)
    assert any("CLAUDE.md" in msg and "validate_fixture_manifest" in msg for msg in drift), drift


def test_audit_detects_missing_token_in_template(mod: ModuleType, tmp_path: Path) -> None:
    _write_all(
        tmp_path,
        makefile_body=("lint:\n\tuv run ruff check .\n\tbash scripts/check_codegen_fresh.sh\n"),
        claude_summary="ruff check + codegen freshness",
        template_summary="ruff check",  # missing codegen
    )
    drift = mod.audit(tmp_path)
    assert any(
        "EXTRACTION_TICKET_TEMPLATE" in msg and "check_codegen_fresh" in msg for msg in drift
    ), drift


def test_audit_fails_closed_on_missing_makefile(mod: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("make lint             # ruff check\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Makefile"):
        mod.audit(tmp_path)


def test_audit_fails_closed_on_missing_claude_md(mod: ModuleType, tmp_path: Path) -> None:
    _write_makefile(tmp_path, "lint:\n\tuv run ruff check .\n")
    with pytest.raises(RuntimeError, match=r"CLAUDE\.md"):
        mod.audit(tmp_path)


def test_audit_fails_closed_on_missing_template(mod: ModuleType, tmp_path: Path) -> None:
    _write_makefile(tmp_path, "lint:\n\tuv run ruff check .\n")
    (tmp_path / "CLAUDE.md").write_text("make lint             # ruff check\n", encoding="utf-8")
    # No docs/EXTRACTION_TICKET_TEMPLATE.md -> fail closed.
    with pytest.raises(RuntimeError, match="EXTRACTION_TICKET_TEMPLATE"):
        mod.audit(tmp_path)


def test_audit_against_live_repo_is_clean(mod: ModuleType) -> None:
    # Smoke test: the shipped Makefile + CLAUDE.md + template must agree.
    # Regression guard against accidentally reintroducing the S5U-690 drift
    # in a future change to any of the three files.
    assert mod.audit(REPO) == []
