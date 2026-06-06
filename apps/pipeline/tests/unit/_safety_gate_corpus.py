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
    """One adversarial fixture: a code snippet and its expected verdict.

    ``added_lines`` (optional) models a real diff: the 1-based line numbers of
    the snippet that are genuinely ``+``-added rows. When set, a harness feeds
    ONLY those lines as "the diff", leaving the rest as unchanged context. This
    is what makes an enclosing-context detector load-bearing (S5U-921): a
    multiline bare-row addition whose ``added_lines`` exclude the
    token-bearing decorator/import line is detectable only by enclosing context,
    not by a line-grep over the added line's own text. When ``None``, a harness
    is free to treat the whole snippet as the diff.
    """

    policy: str
    id: str
    expect: str
    snippet: str
    note: str | None
    added_lines: tuple[int, ...] | None


def corpus_dir() -> Path:
    """Absolute path to ``apps/pipeline/tests/safety_gate_corpus``."""
    return Path(__file__).resolve().parent.parent / "safety_gate_corpus"


def _parse_added_lines(
    raw_value: object, *, snippet: str, path: Path, case_id: str
) -> tuple[int, ...] | None:
    """Validate the optional ``added_lines`` field; fail-closed on any defect.

    Per ``.claude/rules/guards.md`` Rule G1, a malformed override is a worse
    failure state than an absent one: a string/float/negative/out-of-range value
    must raise rather than silently fall back to whole-snippet (which would
    re-open the S5U-921 false-green). ``None`` (key absent) is the only
    "use whole snippet" signal.
    """
    if raw_value is None:
        return None
    if not isinstance(raw_value, list) or not raw_value:
        raise ValueError(
            f"corpus {path} case {case_id!r} has `added_lines`={raw_value!r}; "
            "must be a non-empty list of 1-based int line numbers"
        )
    max_line = len(snippet.splitlines())
    parsed: list[int] = []
    for entry in raw_value:
        # bool is an int subclass; reject it explicitly so `[true]` cannot
        # masquerade as line 1.
        if isinstance(entry, bool) or not isinstance(entry, int):
            raise ValueError(
                f"corpus {path} case {case_id!r} `added_lines` entry {entry!r} "
                "is not an int line number"
            )
        if entry < 1 or entry > max_line:
            raise ValueError(
                f"corpus {path} case {case_id!r} `added_lines` entry {entry} "
                f"is out of range 1..{max_line} for the snippet"
            )
        parsed.append(entry)
    return tuple(parsed)


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
        added_lines = _parse_added_lines(
            raw.get("added_lines"), snippet=snippet, path=path, case_id=case_id
        )
        cases.append(
            CorpusCase(
                policy=policy,
                id=case_id,
                expect=expect,
                snippet=snippet,
                note=raw.get("note"),
                added_lines=added_lines,
            )
        )
    return cases
