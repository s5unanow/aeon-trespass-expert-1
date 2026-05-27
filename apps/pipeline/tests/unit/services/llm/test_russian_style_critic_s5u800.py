# ruff: noqa: RUF001  — Russian examples are the behavior under test.
"""S5U-800 — Russian monolingual style critic service tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from atr_pipeline.services.llm.russian_style_critic import (
    CriticPageRequest,
    CriticParagraph,
    MockRussianStyleCritic,
)
from atr_pipeline.services.llm.russian_style_critic_codex import (
    CodexRussianStyleCritic,
)
from atr_schemas.enums import Severity
from atr_schemas.translation_style_critic_v1 import TranslationStyleCriticPageV1
from tests.unit.services.llm._codex_cli_helpers import argv_value_after


def _request(*texts: str) -> CriticPageRequest:
    return CriticPageRequest(
        document_id="doc",
        page_id="p0001",
        paragraphs=[
            CriticParagraph(
                paragraph_id=f"p{i:04d}",
                block_type="paragraph",
                ru_text=text,
                source_text="minimal source",
            )
            for i, text in enumerate(texts, start=1)
        ],
    )


def test_mock_critic_flags_known_style_examples() -> None:
    """Known awkward Russian examples produce paragraph-local JSON findings."""
    response = MockRussianStyleCritic().critique_page(
        _request(
            "Он стоял перед дверью с великим трепетом.",
            "Известие быстро обошло древний мегаполис.",
            "Таково было убожество великолепия этого места.",
            "Вы входите в зал. Вы видите статую. Вы слышите шепот.",
            "Но только несколько.",
        )
    )

    findings = response.result.findings
    assert len(findings) >= 5
    assert {f.paragraph_id for f in findings} == {
        "p0001",
        "p0002",
        "p0003",
        "p0004",
        "p0005",
    }
    assert all(f.severity in {Severity.INFO, Severity.WARNING} for f in findings)
    assert all(f.quote and f.why and f.suggestions for f in findings)


def test_mock_critic_keeps_mechanics_and_terminology_drift_out_of_scope() -> None:
    """Term/mechanics drift alone is not a monolingual readability finding."""
    response = MockRussianStyleCritic().critique_page(
        _request("Danger переведено как Угроза, а не как Опасность.")
    )
    assert response.result.findings == []


def test_style_critic_schema_requires_paragraph_id_quote_why_and_suggestions() -> None:
    """The persisted critic JSON contract rejects non-local or empty findings."""
    with pytest.raises(ValidationError):
        TranslationStyleCriticPageV1.model_validate(
            {
                "document_id": "doc",
                "page_id": "p0001",
                "findings": [
                    {
                        "paragraph_id": "p1",
                        "severity": "warning",
                        "quote": "",
                        "why": "Too vague.",
                        "suggestions": [],
                    }
                ],
            }
        )


def test_codex_critic_parses_schema_valid_json() -> None:
    """Codex critic validates the final message against TranslationStyleCriticPageV1."""
    payload = json.dumps(
        {
            "document_id": "doc",
            "page_id": "p0001",
            "findings": [
                {
                    "paragraph_id": "p0001",
                    "severity": "warning",
                    "quote": "с великим трепетом",
                    "why": "Коллокация звучит канцелярски и тяжело.",
                    "suggestions": ["Заменить на «с благоговейным трепетом»."],
                }
            ],
        },
        ensure_ascii=False,
    )

    def _side(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        last_msg_path = argv_value_after(argv, "--output-last-message")
        schema_path = argv_value_after(argv, "--output-schema")
        assert last_msg_path is not None
        assert schema_path is not None
        assert Path(schema_path).is_file()
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        assert "schema_version" in schema["required"]
        assert sorted(schema["required"]) == sorted(schema["properties"])
        Path(last_msg_path).write_text(payload, encoding="utf-8")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    critic = CodexRussianStyleCritic(model="gpt-5.5", reasoning_effort="high")
    with patch(
        "atr_pipeline.services.llm.russian_style_critic_codex.subprocess.run",
        side_effect=_side,
    ):
        response = critic.critique_page(_request("с великим трепетом"))

    assert response.result.findings[0].paragraph_id == "p0001"
    assert response.meta.provider == "codex-cli"
    assert response.meta.model == "gpt-5.5"
    assert response.meta.extra["reasoning_effort"] == "high"


def test_codex_critic_rejects_malformed_json() -> None:
    """Malformed or schema-invalid Codex output is a hard failure."""
    critic = CodexRussianStyleCritic(model="gpt-5.5")

    def _side(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        argv = args[0]
        assert isinstance(argv, list)
        last_msg_path = argv_value_after(argv, "--output-last-message")
        assert last_msg_path is not None
        Path(last_msg_path).write_text('{"findings": "wrong"}', encoding="utf-8")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    with (
        patch(
            "atr_pipeline.services.llm.russian_style_critic_codex.subprocess.run",
            side_effect=_side,
        ),
        pytest.raises(ValidationError),
    ):
        critic.critique_page(_request("текст"))
