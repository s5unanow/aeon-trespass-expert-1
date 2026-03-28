"""Conservative text normalization applied after span merge.

Fixes three classes of post-extraction artifacts:
- Line-break hyphenation (``some- thing`` → ``something``)
- BEL / control-character remnants
- Missing sentence-boundary spacing (``end.Start`` → ``end. Start``)
"""

from __future__ import annotations

import re

from atr_schemas.page_ir_v1 import TextInline

# ── Control-character cleanup ────────────────────────────────────────
# C0 block (except HT, LF, CR) plus DEL.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# ── Dehyphenation ────────────────────────────────────────────────────
# Pattern produced by span merge when a line ends with a hyphen:
# one or more letters, hyphen, *space*, then a lowercase letter.
# Real in-word hyphens (``co-op``) have no space after the hyphen.
_LINE_HYPHEN_RE = re.compile(r"([a-zA-Z]+)- ([a-z])")

# Prefixes where the hyphen is almost always structural.  Kept narrow
# to avoid false positives on words like ``under-standing`` or
# ``re-sult``.  Only includes prefixes that are standalone English words
# and are virtually always hyphenated when used as modifiers.
_COMPOUND_PREFIXES = frozenset(
    {
        "co",
        "all",
        "half",
        "non",
        "re",
        "self",
        "well",
    }
)

# ── Glued sentences ──────────────────────────────────────────────────
# Lowercase letter + sentence-end punctuation + uppercase letter,
# with no space between them.  Requiring a preceding lowercase letter
# avoids false positives on abbreviations like ``U.S.``.
_GLUED_SENTENCE_RE = re.compile(r"([a-z])([.!?])([A-Z])")


def _strip_control_chars(text: str) -> str:
    """Remove BEL and other non-printable control characters."""
    return _CONTROL_CHAR_RE.sub("", text)


def _dehyphenate(text: str) -> str:
    """Rejoin words split by line-break hyphens.

    Preserves hyphens for known compound prefixes (e.g. ``co-op``,
    ``re-roll``, ``well-known``).
    """

    def _replace(m: re.Match[str]) -> str:
        left_word = m.group(1)
        right_char = m.group(2)
        if left_word.lower() in _COMPOUND_PREFIXES:
            return f"{left_word}-{right_char}"
        return f"{left_word}{right_char}"

    return _LINE_HYPHEN_RE.sub(_replace, text)


def _fix_glued_sentences(text: str) -> str:
    """Insert space between sentence-end punctuation and next sentence."""
    return _GLUED_SENTENCE_RE.sub(r"\1\2 \3", text)


def normalize_text(text: str) -> str:
    """Apply all conservative normalizations to *text*."""
    text = _strip_control_chars(text)
    text = _dehyphenate(text)
    return _fix_glued_sentences(text)


def normalize_text_inlines(
    inlines: list[TextInline],
) -> list[TextInline]:
    """Return a new list with normalized text content in each inline."""
    result: list[TextInline] = []
    for ti in inlines:
        cleaned = normalize_text(ti.text)
        if cleaned == ti.text:
            result.append(ti)
        else:
            result.append(
                TextInline(
                    text=cleaned,
                    marks=ti.marks,
                    lang=ti.lang,
                    source_word_ids=ti.source_word_ids,
                )
            )
    return result
