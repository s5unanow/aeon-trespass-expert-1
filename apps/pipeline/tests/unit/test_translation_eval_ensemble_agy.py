# ruff: noqa: RUF001  — Cyrillic expected strings are intentional.
"""Tests for the S5U-776 AGY ensemble runner helpers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[4]


@pytest.fixture()
def ensemble_mod() -> ModuleType:
    repo_str = str(REPO)
    added = repo_str not in sys.path
    if added:
        sys.path.insert(0, repo_str)
    try:
        return importlib.import_module("scripts.translation_eval.ensemble_poc")
    finally:
        if added:
            sys.path.remove(repo_str)


def test_build_agy_argv_uses_print_timeout(ensemble_mod: ModuleType) -> None:
    argv = ensemble_mod._build_agy_argv(  # type: ignore[attr-defined]
        executable="/tmp/agy",
        prompt="translate",
        timeout="15m",
    )

    assert argv == ["/tmp/agy", "--print-timeout", "15m", "--print", "translate"]


def test_duration_parser_accepts_agy_default_shape(ensemble_mod: ModuleType) -> None:
    assert ensemble_mod._duration_to_seconds("5m0s") == 300  # type: ignore[attr-defined]
    assert ensemble_mod._duration_to_seconds("15m") == 900  # type: ignore[attr-defined]
    assert ensemble_mod._duration_to_seconds("900s") == 900  # type: ignore[attr-defined]


def test_agy_stdout_error_detection(ensemble_mod: ModuleType) -> None:
    assert ensemble_mod._looks_like_agy_error(  # type: ignore[attr-defined]
        "Error: timed out waiting for response"
    )


def test_process_page_runs_three_agy_variants_and_final_editor(
    ensemble_mod: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_dir = tmp_path / "translation-eval"
    eval_dir.mkdir()
    (eval_dir / "page-1-en.txt").write_text("So it begins\n\nSee 0068.", encoding="utf-8")
    out_dir = tmp_path / "out"
    agy_stages: list[str] = []
    opus_stages: list[str] = []

    def fake_agy(**kwargs: object) -> tuple[str, object]:
        stage = str(kwargs["stage"])
        agy_stages.append(stage)
        return f"Вариант {len(agy_stages)}.\n\nПерейдите к 0068.", ensemble_mod.CallRecord(
            stage=stage,
            model="gemini-pro-high",
            wall_seconds=0.1,
            input_tokens=0,
            output_tokens=0,
        )

    def fake_anthropic(_client: Any, **kwargs: object) -> tuple[str, object]:
        stage = str(kwargs["stage"])
        opus_stages.append(stage)
        text = "Так берет свое начало это сказание.\n\nПерейдите к 0068."
        return text, ensemble_mod.CallRecord(
            stage=stage,
            model=str(kwargs["model"]),
            wall_seconds=0.1,
            input_tokens=1,
            output_tokens=1,
        )

    monkeypatch.setattr(ensemble_mod, "EVAL_DIR", eval_dir)
    monkeypatch.setattr(ensemble_mod, "_read_gemma_witness", lambda _page: "")
    monkeypatch.setattr(ensemble_mod, "_call_agy", fake_agy)
    monkeypatch.setattr(ensemble_mod, "_call_anthropic", fake_anthropic)

    result = ensemble_mod._process_page(  # type: ignore[attr-defined]
        object(),
        1,
        out_dir,
        agy_executable="/tmp/agy",
        agy_timeout="15m",
        opus_model="claude-opus-4-20250514",
    )

    assert len(agy_stages) == 3
    assert opus_stages == ["opus-synthesis:page-1", "opus-editor:page-1"]
    assert result.synth_v2 == "Так берет свое начало это сказание.\n\nПерейдите к 0068."
    assert (out_dir / "agy" / "page-1-literary-prose.txt").is_file()
    assert (out_dir / "opus" / "page-1-synth-v2.txt").is_file()
    assert (out_dir / "qa" / "page-1-qa-v2.json").is_file()
