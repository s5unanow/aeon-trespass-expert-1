"""Loader for the safety-gate adversarial corpus (S5U-789).

Each policy has a named corpus at
``apps/pipeline/tests/safety_gate_corpus/<policy>.toml`` listing accepted and
rejected syntactic equivalents. The corpus is the contract a detector must
satisfy; reviewer-found bypasses are added here as ``block`` cases rather than
patched in as one-off regexes.

Leading-underscore filename: pytest does not collect it as a test module.

Fail-closed (mirrors ``.claude/rules/guards.md`` Rule G1): a missing corpus,
unparseable TOML, missing required key, unknown ``expect`` value, or an empty
case list all raise rather than yielding a silently-empty parametrize set
(an empty parametrize would make a corpus-driven test vacuously pass).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

VALID_EXPECT = frozenset({"block", "allow", "known_residual"})


@dataclass(frozen=True)
class CorpusCase:
    """One adversarial fixture: a code snippet and its expected verdict."""

    policy: str
    id: str
    expect: str
    snippet: str
    note: str | None


def corpus_dir() -> Path:
    """Absolute path to ``apps/pipeline/tests/safety_gate_corpus``."""
    return Path(__file__).resolve().parent.parent / "safety_gate_corpus"


def load_corpus(policy: str) -> list[CorpusCase]:
    """Load and validate every case for ``policy``. Raise on any defect."""
    path = corpus_dir() / f"{policy}.toml"
    if not path.exists():
        raise FileNotFoundError(f"safety-gate corpus not found: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"corpus {path} is not valid TOML: {exc}") from exc

    declared_policy = data.get("policy")
    if declared_policy != policy:
        raise ValueError(f"corpus {path} declares policy={declared_policy!r}, expected {policy!r}")

    raw_cases = data.get("case")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"corpus {path} has no `[[case]]` entries")

    cases: list[CorpusCase] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(raw_cases):
        try:
            case_id = raw["id"]
            expect = raw["expect"]
            snippet = raw["snippet"]
        except KeyError as exc:
            raise ValueError(f"corpus {path} case #{idx} missing key {exc}") from exc
        if expect not in VALID_EXPECT:
            raise ValueError(
                f"corpus {path} case {case_id!r} has unknown expect={expect!r}; "
                f"must be one of {sorted(VALID_EXPECT)}"
            )
        if case_id in seen_ids:
            raise ValueError(f"corpus {path} has duplicate case id {case_id!r}")
        seen_ids.add(case_id)
        cases.append(
            CorpusCase(
                policy=policy,
                id=case_id,
                expect=expect,
                snippet=snippet,
                note=raw.get("note"),
            )
        )
    return cases
