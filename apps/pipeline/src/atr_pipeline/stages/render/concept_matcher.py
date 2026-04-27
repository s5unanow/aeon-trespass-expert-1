"""Concept-mention pattern indexing and span-deduplicated text matching.

Extracted from ``page_builder.py`` (S5U-739) to keep the page-builder
module under the 400-line cap. The two helpers here are the
text-pattern index builder and the longest-match-first span matcher
used by ``_extract_concept_mentions``.
"""

from __future__ import annotations

import re

from atr_schemas.concept_registry_v1 import ConceptRegistryV1


def match_text_patterns(
    text: str,
    patterns: list[tuple[re.Pattern[str], str, int]],
    seen: set[str],
    mentions: list[str],
) -> None:
    """Match text patterns with longest-match-first span deduplication.

    Each pattern carries a specificity score (lower = more specific):
    0 = lemma match, 1 = pattern/surface-form match.
    When spans overlap, the longest match wins; ties broken by specificity.
    """
    hits: list[tuple[int, int, str, int]] = []
    for pattern, concept_id, specificity in patterns:
        for m in pattern.finditer(text):
            hits.append((m.start(), m.end(), concept_id, specificity))

    # Sort: longest span first, then most specific, then earliest position
    hits.sort(key=lambda h: (-(h[1] - h[0]), h[3], h[0]))

    # Greedily accept longest matches; skip overlapping shorter ones
    claimed: list[tuple[int, int]] = []
    for start, end, concept_id, _spec in hits:
        if concept_id in seen:
            continue
        if any(start < ce and end > cs for cs, ce in claimed):
            continue
        claimed.append((start, end))
        seen.add(concept_id)
        mentions.append(concept_id)


def build_text_pattern_index(
    registry: ConceptRegistryV1,
) -> list[tuple[re.Pattern[str], str, int]]:
    """Build compiled regex patterns for text-based concept detection.

    Returns (compiled_pattern, concept_id, specificity) tuples.
    Specificity 0 = lemma match, 1 = pattern/surface-form match.
    """
    index: list[tuple[re.Pattern[str], str, int]] = []
    for concept in registry.concepts:
        lemma_lower = concept.source.lemma.lower()
        for text in (*concept.source.patterns, *concept.target.allowed_surface_forms):
            if text:
                specificity = 0 if text.lower() == lemma_lower else 1
                pat = re.compile(r"\b" + re.escape(text) + r"\b", re.IGNORECASE)
                index.append((pat, concept.concept_id, specificity))
    return index
