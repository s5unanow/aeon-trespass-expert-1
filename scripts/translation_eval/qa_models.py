"""Shared data models for local translation QA."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QAFinding:
    code: str
    detail: str
