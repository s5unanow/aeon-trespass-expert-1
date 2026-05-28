# ruff: noqa: E402,RUF001  — path setup and Russian examples are intentional.
"""Tests for the S5U-802 improved rerun helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from atr_pipeline.services.llm.russian_style_repair import RepairPageRequest, RepairParagraph
from atr_schemas.enums import Severity
from atr_schemas.translation_style_critic_v1 import TranslationStyleCriticFindingV1

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.translation_eval.docx_rollout import (
    DOCX_ROOT,
    build_doc_critic_request,
    validate_docx_out_dir,
    validate_style_reference_path,
)
from scripts.translation_eval.docx_rollout import (
    build_repair_request as build_docx_repair_request,
)
from scripts.translation_eval.improved_rerun import (
    apply_text_repairs,
    build_repair_report,
)
from scripts.translation_eval.improved_rerun_core import (
    POC_ROOT,
    PageRun,
    build_critic_request,
    parse_token_usage,
    validate_out_dir,
)
from scripts.translation_eval.improved_rerun_report import comment_status


def test_build_critic_request_aligns_paragraph_context() -> None:
    request = build_critic_request(
        1,
        "First source.\n\nSecond source.",
        "Первый перевод.\n\nВторой перевод.",
    )

    assert request.document_id == "s5u-776"
    assert request.page_id == "page-1"
    assert [p.paragraph_id for p in request.paragraphs] == ["p001", "p002"]
    assert request.paragraphs[1].source_text == "Second source."
    assert request.paragraphs[1].prev_ru_text == "Первый перевод."


def test_parse_token_usage_reads_final_json_event() -> None:
    stdout = "\n".join(
        [
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}',
            '{"type":"turn.completed","usage":{"input_tokens":15,"output_tokens":7}}',
        ]
    )

    assert parse_token_usage(stdout) == (15, 7)


def test_validate_out_dir_requires_new_poc_subfolder() -> None:
    validate_out_dir(POC_ROOT / "style-v2")

    try:
        validate_out_dir(POC_ROOT)
    except ValueError as exc:
        assert "new subfolder" in str(exc)
    else:
        raise AssertionError("expected POC root to be rejected")


def test_validate_docx_out_dir_requires_new_docx_subfolder() -> None:
    validate_docx_out_dir(DOCX_ROOT / "s5u-803-stabilized")

    try:
        validate_docx_out_dir(DOCX_ROOT)
    except ValueError as exc:
        assert "new subfolder" in str(exc)
    else:
        raise AssertionError("expected DOCX root to be rejected")


def test_validate_style_reference_path_stays_under_docx_root() -> None:
    validate_style_reference_path(DOCX_ROOT / "gemini" / "synth-v2.txt")

    try:
        validate_style_reference_path(Path("/tmp/gemini-style.txt"))
    except ValueError as exc:
        assert "style reference must stay under" in str(exc)
    else:
        raise AssertionError("expected external style reference to be rejected")


def test_build_doc_critic_request_labels_docx_rollout() -> None:
    request = build_doc_critic_request(
        "doc-1",
        "stage-a",
        "First source.\n\nSecond source.",
        "Первый перевод.\n\nВторой перевод.",
    )

    assert request.document_id == "doc-1"
    assert request.page_id == "stage-a"
    assert [p.paragraph_id for p in request.paragraphs] == ["p001", "p002"]
    assert request.paragraphs[1].source_text == "Second source."


def test_docx_repair_request_skips_info_findings() -> None:
    request = build_doc_critic_request(
        "doc-1",
        "stage-a",
        "First source.\n\nSecond source.",
        "Первый перевод.\n\nВторой перевод.",
    )
    info = TranslationStyleCriticFindingV1(
        paragraph_id="p001",
        severity=Severity.INFO,
        quote="Первый перевод",
        why="Minor optional phrasing.",
        suggestions=["Optional rewrite."],
    )
    warning = TranslationStyleCriticFindingV1(
        paragraph_id="p002",
        severity=Severity.WARNING,
        quote="Второй перевод",
        why="Awkward phrasing.",
        suggestions=["Required rewrite."],
    )

    repair_request = build_docx_repair_request(request, [info, warning])

    assert [paragraph.paragraph_id for paragraph in repair_request.paragraphs] == ["p002"]


def test_comment_status_reports_style_qa_improvement() -> None:
    status = comment_status(
        "Отметьте «параграф 0003».",
        'Note "passage 0003."',
        "Запомните «параграф 0003».",
        "Отметьте «параграф 0003».",
    )

    assert status == "improved toward human target"


def test_apply_text_repairs_changes_only_requested_paragraph(tmp_path: Path) -> None:
    _ = tmp_path
    finding = TranslationStyleCriticFindingV1(
        paragraph_id="p001",
        severity=Severity.WARNING,
        quote="с великим трепетом",
        why="Коллокация звучит тяжеловесно.",
        suggestions=["Заменить на естественный оборот."],
    )
    request = RepairPageRequest(
        document_id="s5u-776",
        page_id="page-1",
        paragraphs=[
            RepairParagraph(
                paragraph_id="p001",
                current_text="Они ждут с великим трепетом.",
                findings=[finding],
            )
        ],
    )
    result = PageRun(
        page=1,
        en_text="They wait.\n\nClean.",
        old_final="",
        editor_text="Они ждут с великим трепетом.\n\nЧистый абзац.",
    )

    changes = apply_text_repairs(
        result,
        request,
        {"p001": "Они ждут с замиранием сердца."},
    )
    result.qa_final = []
    report = build_repair_report(request, [finding], changes, result)

    assert result.final_text == "Они ждут с замиранием сердца.\n\nЧистый абзац."
    assert report.repaired_paragraph_ids == ["p001"]
    assert report.skipped_paragraph_ids == []
    assert report.changes[0].finding_quotes == ["с великим трепетом"]
