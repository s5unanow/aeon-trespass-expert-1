#!/usr/bin/env python3
"""Content-derived detector for pre-commit hook-bypass tokens (S5U-822).

S5U-789 child. The hook-bypass policy (CLAUDE.md NEVER list + ``.claude/rules/
hooks.md`` § "Hook-bypass token enumeration") previously had **no script** — it
lived only as the prose-token grep in ``.claude/prompts/review.md`` check #22.
This module gives the policy a machine contract so it can be backed by a named
adversarial corpus (``apps/pipeline/tests/safety_gate_corpus/hook_bypass.toml``),
following the S5U-789 detector-migration pattern (``check_visual_test_overrides.py``).

The detector scans a **text blob** — the merge-time side-channel that review.md
#22 inspects: commit messages on the branch plus the PR body — line by line and
returns one :class:`Violation` per matched line, naming the token class.

**Defense-in-depth, not a replacement.** This is the policy's machine contract;
review.md #22's prose probe stays as the merge-time reviewer gate. The detector
deliberately does NOT grade disclosure (the ``## Hook bypass disclosure``
heading awareness, the docs-citation false-positive carve-outs) — that nuance is
the reviewer's job. It only answers "does this text contain a hook-bypass
token?" so the corpus can pin the token set. See the CI-gating decision in
``.claude/rules/hooks.md`` § "Hook-bypass disclosure" (S5U-822): the
corpus-driven contract test runs inside the existing ``python / test`` job; this
detector is NOT a new required-check context.

Per ``.claude/rules/guards.md``:

- **Rule G1** (fail-closed defaults): ``main()`` exits non-zero on an unreadable
  ``--text-file``, a ``git log`` failure on ``--commit-range``, or no input at
  all (no file, no range, no stdin) — never silently passes "no tokens" on a
  degenerate input.
- **Rule G2** (content-derived sets): the blocked set is whatever matches the
  behavioral token-class regexes below, NOT a hardcoded list of literal command
  strings. A wrapper/rename (``mytool commit --no-verify``), spacing variant
  (``HUSKY=0   git commit``), or short-flag alias (``-n``, ``-c
  core.hooksPath=``) is caught by content, not surface name.

Token classes (one content signature per behavioral class, mirroring the
review.md #22 probe set and the hooks.md enumeration):

* ``cli_no_verify``          — ``--no-verify`` long flag (subsumes ``git commit
  --amend --no-verify`` and any wrapper command, not just ``git commit``).
* ``cli_short_n``            — ``-n`` short flag in word-proximity (<=80 chars,
  either order) to ``commit`` / ``merge`` / ``rebase``. English inflections
  ("committed") do NOT match (review.md #22 line 209).
* ``env_husky``              — ``HUSKY=0``.
* ``env_lefthook``           — ``LEFTHOOK=0``.
* ``env_skip``               — ``SKIP=<hook>`` (selective skip; requires a value).
* ``env_hook_bypass``        — ``HOOK_BYPASS=`` (any value).
* ``env_no_verify``          — ``NO_VERIFY=`` (any value).
* ``env_coordinator_ack``    — ``COORDINATOR_ACK_STATUS_SOURCE=`` (S5U-672).
* ``hook_mutation_chmod``    — ``chmod -x .git/hooks/...``.
* ``hook_mutation_rm``       — ``rm .git/hooks/...``.
* ``hook_mutation_noop``     — prose: replaced/overwrote/swapped a pre-commit /
  hooks file, or "no-op hook" (the ``exit 0`` replacement, review.md #22 lines
  214/216).
* ``hookspath_redirect``     — ``core.hooksPath`` (covers ``git config
  core.hooksPath /x`` AND ``git -c core.hooksPath=/x commit``).

Documented residuals the detector does NOT catch (pinned ``known_residual`` in
the corpus): the bracketed gitconfig-file form ``[core]\\n  hooksPath = ...``
(hooks.md marks it out of scope — no contiguous ``core.hooksPath`` substring);
cross-line prose paraphrases of hook mutation (the per-line scan cannot cross a
blank line). Bare ``no-verify`` noun-phrases without the leading ``--`` are
``allow`` (the detector anchors on the canonical ``--no-verify`` form).

Usage::

    # From a commit range + a PR-body file (the review.md #22 corpus):
    python scripts/check_hook_bypass_tokens.py --commit-range main..HEAD \\
        --pr-body-file /tmp/pr_body.md
    # From a single text file or stdin:
    python scripts/check_hook_bypass_tokens.py --text-file notes.txt
    cat notes.txt | python scripts/check_hook_bypass_tokens.py --stdin
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Content signatures (Rule G2). Each is the behavioral regex for one token     #
# class; the blocked set is whatever matches these, not a literal command list.#
# --------------------------------------------------------------------------- #

# C1 — `--no-verify` long flag as a whole token, any surrounding command.
# Subsumes `git commit --no-verify` and `git commit --amend --no-verify`, and a
# wrapper/rename (`mytool commit --no-verify`) since the flag, not the command,
# is the signature. The leading `--` is required: a bare `no-verify` noun-phrase
# is the canonical-form-narrowing `allow` case (see module docstring).
CLI_NO_VERIFY_RE = re.compile(r"(?<![\w-])--no-verify(?![\w-])")

# C2 — `-n` short flag (alias of `--no-verify`) in word-proximity to a git verb.
# Mirrors review.md #22 line 207: an 80-char window either direction, with the
# `-n` isolated by non-alphanumeric boundaries (a plain `\b-n\b` is unreliable
# because `-` is not a word char). English inflections like "committed" do NOT
# match because `\bcommit\b` requires the exact word and there is no isolated
# `-n` token. `re.DOTALL` lets the window cross newlines (cross-line prose, S5U-648).
_VERB = r"\b(?:commit|merge|rebase)\b"
_SHORT_N = r"(?<![A-Za-z0-9])-n(?![A-Za-z0-9])"
CLI_SHORT_N_RE = re.compile(
    rf"(?:{_VERB}[\s\S]{{0,80}}{_SHORT_N})|(?:{_SHORT_N}[\s\S]{{0,80}}{_VERB})",
)

# C3-C8 — env-var bypass assignments. Each is the var name at a left word
# boundary followed by `=`. HUSKY/LEFTHOOK pin `=0` (the documented disable
# value); SKIP requires a non-empty value (bare `SKIP=` is too collision-prone —
# recorded as an `allow`); HOOK_BYPASS / NO_VERIFY / COORDINATOR_ACK_STATUS_SOURCE
# match any value (hooks.md: "any value; documentary form of intent").
ENV_HUSKY_RE = re.compile(r"(?<![\w])HUSKY=0\b")
ENV_LEFTHOOK_RE = re.compile(r"(?<![\w])LEFTHOOK=0\b")
ENV_SKIP_RE = re.compile(r"(?<![\w])SKIP=\S")
ENV_HOOK_BYPASS_RE = re.compile(r"(?<![\w])HOOK_BYPASS=")
ENV_NO_VERIFY_RE = re.compile(r"(?<![\w])NO_VERIFY=")
ENV_COORDINATOR_ACK_RE = re.compile(r"(?<![\w])COORDINATOR_ACK_STATUS_SOURCE=")

# C9-C10 — hook-file mutation. `.*` between the command and `.git/hooks` covers
# extra flags / path forms (`chmod -x ./.git/hooks/pre-commit`, etc.).
HOOK_CHMOD_RE = re.compile(r"\bchmod\s+-x\b.*\.git/hooks")
HOOK_RM_RE = re.compile(r"\brm\s.*\.git/hooks")

# C11 — no-op hook replacement, expressed in prose (the `exit 0` stub). Mirrors
# review.md #22 lines 214/216 prose probes; per-line (`.` does not cross
# newlines — the cross-line paraphrase is a documented `known_residual`).
HOOK_NOOP_REPLACE_RE = re.compile(r"(?:replac|overwr|swap)\w*.{0,40}(?:pre-commit|hooks/)")
HOOK_NOOP_PHRASE_RE = re.compile(r"no[- ]op.{0,40}(?:hook|pre-commit)")

# C12 — hook-path redirection. The literal `core.hooksPath` substring covers
# `git config core.hooksPath /x` AND `git -c core.hooksPath=/x commit`
# (review.md #22 line 200). The bracketed `[core]\n hooksPath = ...` gitconfig
# form has no contiguous `core.hooksPath` substring and is the documented
# out-of-scope `known_residual`.
HOOKSPATH_REDIRECT_RE = re.compile(r"core\.hooksPath")


# Ordered (token_class, compiled_regex) tuple driving the per-line scan. Order
# is informational; any match counts the line as a violation of that class. The
# FIRST matching class names the violation (deterministic, stable for the corpus).
TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cli_no_verify", CLI_NO_VERIFY_RE),
    ("env_husky", ENV_HUSKY_RE),
    ("env_lefthook", ENV_LEFTHOOK_RE),
    ("env_skip", ENV_SKIP_RE),
    ("env_hook_bypass", ENV_HOOK_BYPASS_RE),
    ("env_no_verify", ENV_NO_VERIFY_RE),
    ("env_coordinator_ack", ENV_COORDINATOR_ACK_RE),
    ("hook_mutation_chmod", HOOK_CHMOD_RE),
    ("hook_mutation_rm", HOOK_RM_RE),
    ("hook_mutation_noop", HOOK_NOOP_REPLACE_RE),
    ("hook_mutation_noop", HOOK_NOOP_PHRASE_RE),
    ("hookspath_redirect", HOOKSPATH_REDIRECT_RE),
)


@dataclass(frozen=True)
class Violation:
    """A single hook-bypass token hit on one line of the scanned text."""

    line: int
    token_class: str
    excerpt: str

    def format(self) -> str:
        return f"line {self.line}: {self.token_class}: {self.excerpt.strip()!r}"


def _scan_line(line: str) -> str | None:
    """Return the token class of the first per-line pattern that matches `line`.

    Per-line patterns only (C1, C3-C12). The cross-line `-n` proximity class
    (C2) is handled in :func:`scan` against the whole blob, since its 80-char
    window may span a newline.
    """
    for token_class, pattern in TOKEN_PATTERNS:
        if pattern.search(line):
            return token_class
    return None


def scan(text: str) -> list[Violation]:
    """Scan a text blob for hook-bypass tokens. Pure; never raises.

    Production entry point (the corpus contract test drives this directly). The
    file-IO degenerate cases that must fail closed (Rule G1) live in
    :func:`main`, not here — ``scan`` takes an already-materialized string.

    Per-line patterns are matched line by line so violations carry a 1-based
    line number. The cross-line ``-n`` word-proximity class (C2) is matched
    against the whole blob and attributed to the line where the ``-n`` flag
    appears.
    """
    lines = text.splitlines()
    violations: list[Violation] = []
    flagged_lines: set[int] = set()

    for idx, line in enumerate(lines, start=1):
        token_class = _scan_line(line)
        if token_class is not None:
            violations.append(Violation(line=idx, token_class=token_class, excerpt=line))
            flagged_lines.add(idx)

    # C2: cross-line `-n` proximity over the whole blob. Attribute each match to
    # the line carrying the isolated `-n` flag, deduping against per-line hits so
    # a single line is not double-reported.
    for match in CLI_SHORT_N_RE.finditer(text):
        n_pos = _find_isolated_n(text, match.start(), match.end())
        if n_pos is None:
            continue
        line_no = text.count("\n", 0, n_pos) + 1
        if line_no in flagged_lines:
            continue
        excerpt = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
        violations.append(Violation(line=line_no, token_class="cli_short_n", excerpt=excerpt))
        flagged_lines.add(line_no)

    return sorted(violations, key=lambda v: (v.line, v.token_class))


def _find_isolated_n(text: str, start: int, end: int) -> int | None:
    """Return the index of the isolated ``-n`` flag within ``text[start:end]``."""
    region = text[start:end]
    local = _SHORT_N_SEARCH.search(region)
    return start + local.start() if local is not None else None


_SHORT_N_SEARCH = re.compile(_SHORT_N)


def _read_commit_range(commit_range: str) -> str:
    """Return concatenated commit-message bodies for ``commit_range``.

    Fail closed (Rule G1): a ``git log`` non-zero exit (bad range, shallow
    checkout) raises ``RuntimeError`` rather than returning empty text — an
    empty result would silently pass the "no tokens" verdict on a broken input.
    """
    result = subprocess.run(
        ["git", "log", "--format=%B", commit_range],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git log failed for range '{commit_range}': {result.stderr.strip()}. "
            "The range may be unresolvable (shallow checkout) — pass --text-file "
            "or --stdin, or set fetch-depth: 0."
        )
    return result.stdout


def _gather_text(args: argparse.Namespace) -> str:
    """Materialize the scan text from CLI inputs. Fail closed on no input (G1)."""
    parts: list[str] = []
    if args.commit_range:
        parts.append(_read_commit_range(args.commit_range))
    if args.text_file:
        try:
            parts.append(args.text_file.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RuntimeError(f"cannot read --text-file {args.text_file}: {exc}") from exc
    if args.pr_body_file:
        try:
            parts.append(args.pr_body_file.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RuntimeError(f"cannot read --pr-body-file {args.pr_body_file}: {exc}") from exc
    if args.stdin:
        parts.append(sys.stdin.read())
    if not parts:
        raise RuntimeError(
            "no input: pass at least one of --commit-range, --text-file, "
            "--pr-body-file, or --stdin. Refusing to pass on empty input (Rule G1)."
        )
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit-range",
        help="git revision range whose commit-message bodies are scanned (e.g. main..HEAD).",
    )
    parser.add_argument(
        "--text-file",
        type=Path,
        help="A text file to scan (e.g. an exported PR body).",
    )
    parser.add_argument(
        "--pr-body-file",
        type=Path,
        help="A PR-body file to scan alongside other inputs.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Also read text to scan from standard input.",
    )
    args = parser.parse_args(argv)

    try:
        text = _gather_text(args)
    except RuntimeError as exc:
        print(f"::error::hook-bypass-tokens: {exc}", file=sys.stderr)
        return 2

    violations = scan(text)
    if violations:
        print(
            "::error::hook-bypass-tokens: detected pre-commit hook-bypass "
            "token(s) in the scanned text. Per CLAUDE.md NEVER list, a hook "
            "bypass requires a '## Hook bypass disclosure' heading in the PR "
            "body. Concealment grades stronger than the bypass itself "
            "(.claude/rules/hooks.md). Violations:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v.format()}", file=sys.stderr)
        return 1

    print("hook-bypass-tokens: clean (no hook-bypass tokens in the scanned text).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
