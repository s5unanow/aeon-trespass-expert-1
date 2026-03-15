"""Load ConceptRegistryV1 from TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from atr_schemas.concept_registry_v1 import (
    ConceptRegistryV1,
    ConceptSource,
    ConceptTarget,
    ConceptV1,
    ValidationPolicy,
)


def load_concept_registry(path: Path) -> ConceptRegistryV1:
    """Load a concept registry from a TOML file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    concepts: list[ConceptV1] = []
    for c in raw.get("concepts", []):
        source_data = c.get("source", {})
        target_data = c.get("target", {})
        policy_data = c.get("validation_policy", {})

        concepts.append(
            ConceptV1(
                concept_id=c["concept_id"],
                kind=c.get("kind", "term"),
                version=raw.get("version", ""),
                source=ConceptSource(
                    lang=source_data.get("lang", "en"),
                    lemma=source_data.get("lemma", ""),
                    aliases=source_data.get("aliases", []),
                    patterns=source_data.get("patterns", []),
                ),
                target=ConceptTarget(
                    lang=target_data.get("lang", "ru"),
                    lemma=target_data.get("lemma", ""),
                    allowed_surface_forms=target_data.get("allowed_surface_forms", []),
                ),
                icon_binding=c.get("icon_binding"),
                forbidden_targets=c.get("forbidden_targets", []),
                validation_policy=(
                    ValidationPolicy(**policy_data) if policy_data else ValidationPolicy()
                ),
                notes=c.get("notes", ""),
            )
        )

    return ConceptRegistryV1(
        version=raw.get("version", ""),
        concepts=concepts,
    )
