"""S5U-927: corpus .toml files are themselves safety-gate-scoped.

Closes the chained corpus-drop bypass: the safety-gate scope is the union of a
name-derived static regex and the content-derived corpus `detector_sources` union
(S5U-922). The corpus `.toml` files feed that union, so they cannot protect
themselves via it — a worker could drop a `detector_sources` entry to shrink the
union and the shrink itself would be unprotected. The fix adds the corpus dir to
the STATIC regex in BOTH matchers (a self-protection clause, analogous to
`scripts/_detector_source_scope.py`), kept byte-for-byte synced.

This file covers:
  1. The Python `SAFETY_GATE_REGEX` matches corpus .toml and rejects near-misses.
  2. `safety_gate_hits` puts a corpus .toml into scope.
  3. The verbatim-sync guard: the bash hook's anchored-alternation grep body is
     byte-identical to the Python `SAFETY_GATE_REGEX.pattern`. Nothing enforced
     this before S5U-927; since this PR edits both copies, the sync guard is the
     structural backstop against future drift.

Red-before confirmation: ran locally at HEAD^ (corpus clause reverted from both
matchers); output for the corpus-.toml MATCH cases: `safety_gate_hits([...]) == []`
(expected `[path]`) and `SAFETY_GATE_REGEX.match(corpus_toml) is None`; the
sync-guard test passed under the pre-fix state too (both copies lacked the clause
in agreement) and would fail if only one copy were edited.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "pre-pr-check.sh"

CORPUS_TOML = "apps/pipeline/tests/safety_gate_corpus/parametrize_red_before.toml"


@pytest.mark.parametrize(
    "path",
    [
        "apps/pipeline/tests/safety_gate_corpus/parametrize_red_before.toml",
        "apps/pipeline/tests/safety_gate_corpus/hook_bypass.toml",
        "apps/pipeline/tests/safety_gate_corpus/instruction_drift.toml",
        # Nested corpus path: `.+\.toml$` captures any depth under the corpus dir.
        # No nested subdir exists today; if one is ever added it is in scope by
        # default (strictly more protective — fail-closed direction).
        "apps/pipeline/tests/safety_gate_corpus/sub/nested.toml",
    ],
)
def test_safety_gate_regex_matches_corpus_toml(mod: ModuleType, path: str) -> None:
    """S5U-927: every corpus .toml is in safety-gate scope via the static clause."""
    assert mod.SAFETY_GATE_REGEX.match(path), f"expected {path!r} to match"
    assert mod.safety_gate_hits([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        # Non-.toml file inside the corpus dir → NOT captured (only .toml).
        "apps/pipeline/tests/safety_gate_corpus/README.md",
        # `.toml.bak` → NOT captured ($ anchors `.toml` at end-of-path).
        "apps/pipeline/tests/safety_gate_corpus/parametrize_red_before.toml.bak",
        # A .toml elsewhere in the tree → NOT captured (scoped to corpus dir only;
        # no over-capture of configs / fixtures / pyproject).
        "configs/base.toml",
        "apps/pipeline/tests/other_dir/foo.toml",
        # Prefix-evasion: a corpus-looking path under docs/ → NOT captured (the
        # `^` anchor in the full alternation pins the corpus prefix to the start).
        "docs/apps/pipeline/tests/safety_gate_corpus/x.toml",
    ],
)
def test_safety_gate_regex_rejects_corpus_near_misses(mod: ModuleType, path: str) -> None:
    """S5U-927: the corpus clause does not over-capture (Rule G2 scoping)."""
    assert mod.SAFETY_GATE_REGEX.match(path) is None, f"expected {path!r} NOT to match"
    assert mod.safety_gate_hits([path]) == []


def _extract_bash_safety_gate_body(hook_text: str) -> str:
    """Extract the anchored-alternation body from the hook's `| grep -E '^(...)'`.

    Mirrors the extraction in scripts/test_pre_pr_safety_gate.sh so this guard
    asserts the SAME bash surface that the live hook (and the shell harness) use.
    """
    match = re.search(r"\| grep -E '(\^\([^']+\))'", hook_text)
    assert match is not None, "could not locate the safety-gate grep in pre-pr-check.sh"
    return match.group(1)


def test_bash_and_python_safety_gate_regex_are_verbatim_synced(mod: ModuleType) -> None:
    """S5U-927 verbatim-sync guard: the two matchers MUST express the same pattern.

    The bash hook (`.claude/hooks/pre-pr-check.sh`) and the Python audit
    (`scripts/check_post_merge_coordinator_ack.py::SAFETY_GATE_REGEX`) are two
    independent copies of the safety-gate static regex. They are kept in sync only
    by code-review discipline today; this test makes drift mechanically detectable
    inside `python / test`. A one-sided edit to either copy fails here.
    """
    bash_body = _extract_bash_safety_gate_body(HOOK_PATH.read_text(encoding="utf-8"))
    assert bash_body == mod.SAFETY_GATE_REGEX.pattern, (
        "Safety-gate regex drift between the bash hook and the Python audit.\n"
        f"  bash (.claude/hooks/pre-pr-check.sh): {bash_body}\n"
        f"  python (SAFETY_GATE_REGEX):           {mod.SAFETY_GATE_REGEX.pattern}\n"
        "Keep both copies byte-identical (same branches, same order)."
    )
