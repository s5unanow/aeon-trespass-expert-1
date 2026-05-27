"""Tests for scripts/translation_eval/prompts.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]


@pytest.fixture()
def prompts_mod() -> ModuleType:
    repo_str = str(REPO)
    added = repo_str not in sys.path
    if added:
        sys.path.insert(0, repo_str)
    try:
        return importlib.import_module("scripts.translation_eval.prompts")
    finally:
        if added:
            sys.path.remove(repo_str)


def test_prompts_include_s5u798_scene_function_and_rhythm_rules(
    prompts_mod: ModuleType,
) -> None:
    prompt = prompts_mod.build_variant_system_prompt(prompts_mod.TRANSLATION_VARIANTS[1])

    assert "передовой отряд" in prompt
    assert "ignore English syntax" in prompt
    assert "вооружённый эскорт" in prompt
