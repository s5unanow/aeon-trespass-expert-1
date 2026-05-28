"""S5U-803 stabilized rollout for the extracted DOCX translation sample.

The source DOCX itself remains outside the repo. This runner consumes the
already-extracted plain text under ``tmp/translation-eval/give-me-original-
text-now/inputs/source-en-clean.txt`` and writes a new local-only artifact
folder under the same gitignored scratch root.

Run from repo root:
    uv run python -m scripts.translation_eval.docx_rollout
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import defaultdict
from pathlib import Path

from atr_pipeline.services.llm.russian_style_critic import (
    CriticPageRequest,
    CriticParagraph,
)
from atr_pipeline.services.llm.russian_style_critic_codex import (
    CodexRussianStyleCritic,
)
from atr_pipeline.services.llm.russian_style_repair import (
    RepairPageRequest,
    repair_paragraph_from_critic,
)
from atr_pipeline.services.llm.russian_style_repair_codex import (
    CodexRussianStyleRepair,
)
from atr_schemas.enums import Severity
from atr_schemas.translation_style_critic_v1 import (
    TranslationStyleCriticFindingV1,
    TranslationStyleCriticPageV1,
)

from .docx_rollout_report import write_report
from .improved_rerun import apply_text_repairs, build_repair_report
from .improved_rerun_core import (
    DEFAULT_MODEL,
    EVAL_DIR,
    REPO_ROOT,
    CallRecord,
    CodexOptions,
    PageRun,
    adapter_codex_executable,
    call_codex_text,
    qa_as_json,
    split_paragraphs,
    text_prompt,
    write_json,
)
from .prompts import (
    TRANSLATION_VARIANTS,
    build_opus_repair_system_prompt,
    build_opus_repair_user_message,
    build_opus_synthesis_system_prompt,
    build_opus_synthesis_user_message,
    build_variant_system_prompt,
)
from .qa_checks import QAFinding, all_checks

log = logging.getLogger("translation_eval.docx_rollout")

DOCX_ROOT = EVAL_DIR / "give-me-original-text-now"
DEFAULT_SOURCE = DOCX_ROOT / "inputs" / "source-en-clean.txt"
DEFAULT_STYLE_REFERENCE = DOCX_ROOT / "gemini" / "synth-v2.txt"
DEFAULT_OUT_DIR = DOCX_ROOT / "s5u-803-stabilized"
DOCUMENT_ID = "give-me-original-text-now"
PAGE_ID = "docx"


def validate_docx_out_dir(out_dir: Path) -> None:
    root = DOCX_ROOT.resolve()
    target = out_dir.resolve()
    if target == root or root not in target.parents:
        msg = (
            "S5U-803 DOCX output must be a new subfolder under "
            f"{DOCX_ROOT.relative_to(REPO_ROOT)}; got {out_dir}"
        )
        raise ValueError(msg)


def validate_style_reference_path(path: Path | None) -> None:
    if path is None:
        return
    root = DOCX_ROOT.resolve()
    target = path.resolve()
    if target == root or root not in target.parents:
        msg = f"S5U-803 style reference must stay under {DOCX_ROOT.relative_to(REPO_ROOT)}"
        raise ValueError(msg)


def build_doc_critic_request(
    document_id: str,
    page_id: str,
    source_text: str,
    ru_text: str,
) -> CriticPageRequest:
    source_paras = split_paragraphs(source_text)
    ru_paras = split_paragraphs(ru_text)
    paragraphs: list[CriticParagraph] = []
    for index, ru_para in enumerate(ru_paras):
        paragraphs.append(
            CriticParagraph(
                paragraph_id=f"p{index + 1:03d}",
                block_type="paragraph",
                ru_text=ru_para,
                source_text=source_paras[index] if index < len(source_paras) else "",
                prev_ru_text=ru_paras[index - 1] if index > 0 else "",
                next_ru_text=ru_paras[index + 1] if index + 1 < len(ru_paras) else "",
            )
        )
    return CriticPageRequest(document_id=document_id, page_id=page_id, paragraphs=paragraphs)


def run_docx_rollout(
    source_path: Path,
    out_dir: Path,
    *,
    options: CodexOptions,
    style_reference_path: Path | None = None,
) -> PageRun:
    source_text = source_path.read_text(encoding="utf-8")
    validate_style_reference_path(style_reference_path)
    result = PageRun(page=0, en_text=source_text, old_final="")
    _write_input_copy(source_path, source_text, out_dir)

    result.synth_v1 = run_synthesis(
        source_text,
        run_variants(source_text, out_dir, options=options, calls=result.calls),
        out_dir,
        options=options,
        calls=result.calls,
    )
    result.qa_v1 = all_checks(source_text, result.synth_v1, gemma_ru=None)
    write_json(out_dir / "qa" / "qa-v1.json", qa_as_json(result.qa_v1))

    style_reference = _read_optional_style_reference(style_reference_path)
    result.editor_text = run_editor(
        source_text,
        result.synth_v1,
        result.qa_v1,
        style_reference,
        out_dir,
        options=options,
        calls=result.calls,
    )
    result.qa_editor = all_checks(source_text, result.editor_text, gemma_ru=None)
    write_json(out_dir / "qa" / "qa-editor.json", qa_as_json(result.qa_editor))

    critic_request = build_doc_critic_request(
        DOCUMENT_ID,
        PAGE_ID,
        source_text,
        result.editor_text,
    )
    adapter_executable = adapter_codex_executable(out_dir, options)
    critic_result = run_critic(critic_request, options, adapter_executable, result.calls)
    result.critic_findings = len(critic_result.findings)
    write_json(out_dir / "critic" / "critic.json", critic_result)

    run_repair(
        critic_request,
        list(critic_result.findings),
        result,
        out_dir,
        options,
        adapter_executable,
    )
    write_json(out_dir / "qa" / "qa-final.json", qa_as_json(result.qa_final))
    write_report(result, out_dir, options, source_path, style_reference_path)
    return result


def _write_input_copy(source_path: Path, source_text: str, out_dir: Path) -> None:
    inputs_dir = out_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    (inputs_dir / source_path.name).write_text(source_text, encoding="utf-8")


def _read_optional_style_reference(path: Path | None) -> str:
    if path is None:
        return ""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def run_variants(
    source_text: str,
    out_dir: Path,
    *,
    options: CodexOptions,
    calls: list[CallRecord],
) -> list[tuple[str, str]]:
    variants: list[tuple[str, str]] = []
    for variant in TRANSLATION_VARIANTS:
        text, call = call_codex_text(
            text_prompt(build_variant_system_prompt(variant), source_text),
            stage=f"codex-variant:{variant.name}:{PAGE_ID}",
            options=options,
        )
        path = out_dir / "variants" / f"{variant.name}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        variants.append((variant.name, text))
        calls.append(call)
    return variants


def run_synthesis(
    source_text: str,
    variants: list[tuple[str, str]],
    out_dir: Path,
    *,
    options: CodexOptions,
    calls: list[CallRecord],
) -> str:
    user_message = build_opus_synthesis_user_message(source_text, variants)
    text, call = call_codex_text(
        text_prompt(build_opus_synthesis_system_prompt(), user_message),
        stage=f"codex-synthesis:{PAGE_ID}",
        options=options,
    )
    calls.append(call)
    (out_dir / "synthesis").mkdir(parents=True, exist_ok=True)
    (out_dir / "synthesis" / "synth-v1.txt").write_text(text + "\n", encoding="utf-8")
    return text


def run_editor(
    source_text: str,
    synth_v1: str,
    findings: list[QAFinding],
    style_reference: str,
    out_dir: Path,
    *,
    options: CodexOptions,
    calls: list[CallRecord],
) -> str:
    user_message = build_opus_repair_user_message(
        source_text,
        synth_v1,
        [f"{f.code}: {f.detail}" for f in findings],
    )
    if style_reference:
        user_message = "\n\n".join(
            [
                user_message,
                "OPTIONAL GEMINI STYLE REFERENCE:",
                style_reference.rstrip(),
                "Use the reference only for Russian rhythm ideas that preserve "
                "the source and pipeline structure. Do not copy reordered blocks, "
                "mechanics errors, or terminology drift from the reference.",
            ]
        )
    text, call = call_codex_text(
        text_prompt(build_opus_repair_system_prompt(), user_message),
        stage=f"codex-editor:{PAGE_ID}",
        options=options,
    )
    calls.append(call)
    (out_dir / "editor").mkdir(parents=True, exist_ok=True)
    (out_dir / "editor" / "editor.txt").write_text(text + "\n", encoding="utf-8")
    return text


def run_critic(
    request: CriticPageRequest,
    options: CodexOptions,
    adapter_executable: str,
    calls: list[CallRecord],
) -> TranslationStyleCriticPageV1:
    critic = CodexRussianStyleCritic(
        model=options.model,
        timeout_seconds=options.timeout_seconds,
        reasoning_effort=options.reasoning_effort,
        executable=adapter_executable,
    )
    t0 = time.perf_counter()
    response = critic.critique_page(request)
    calls.append(
        CallRecord(
            stage=f"codex-style-critic:{PAGE_ID}",
            model=options.model,
            wall_seconds=round(time.perf_counter() - t0, 2),
            input_tokens=response.meta.input_tokens,
            output_tokens=response.meta.output_tokens,
        )
    )
    return response.result


def run_repair(
    critic_request: CriticPageRequest,
    findings: list[TranslationStyleCriticFindingV1],
    result: PageRun,
    out_dir: Path,
    options: CodexOptions,
    adapter_executable: str,
) -> None:
    repair_request = build_repair_request(critic_request, findings)
    repairs: dict[str, str] = {}
    if repair_request.paragraphs:
        repair = CodexRussianStyleRepair(
            model=options.model,
            timeout_seconds=options.timeout_seconds,
            reasoning_effort=options.reasoning_effort,
            executable=adapter_executable,
        )
        t0 = time.perf_counter()
        response = repair.repair_page(repair_request)
        result.calls.append(
            CallRecord(
                stage=f"codex-style-repair:{PAGE_ID}",
                model=options.model,
                wall_seconds=round(time.perf_counter() - t0, 2),
                input_tokens=response.meta.input_tokens,
                output_tokens=response.meta.output_tokens,
            )
        )
        repairs = {item.paragraph_id: item.repaired_text for item in response.result.repairs}

    changes = apply_text_repairs(result, repair_request, repairs)
    result.qa_final = all_checks(result.en_text, result.final_text, gemma_ru=None)
    report = build_repair_report(repair_request, findings, changes, result)
    result.repaired_ids = report.repaired_paragraph_ids
    write_json(out_dir / "repair" / "repair-report.json", report)
    final_dir = out_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "synth-v2.txt").write_text(result.final_text + "\n", encoding="utf-8")


def build_repair_request(
    critic_request: CriticPageRequest,
    findings: list[TranslationStyleCriticFindingV1],
) -> RepairPageRequest:
    findings_by_id: dict[str, list[TranslationStyleCriticFindingV1]] = defaultdict(list)
    for finding in findings:
        if finding.severity == Severity.INFO:
            continue
        findings_by_id[finding.paragraph_id].append(finding)
    paragraphs = [
        repair_paragraph_from_critic(paragraph, findings_by_id[paragraph.paragraph_id])
        for paragraph in critic_request.paragraphs
        if findings_by_id.get(paragraph.paragraph_id)
    ]
    return RepairPageRequest(
        document_id=critic_request.document_id,
        page_id=critic_request.page_id,
        paragraphs=paragraphs,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument(
        "--style-reference",
        type=Path,
        default=None,
        help=f"Optional style reference, e.g. {DEFAULT_STYLE_REFERENCE}",
    )
    args = parser.parse_args(argv)

    validate_docx_out_dir(args.out_dir)
    validate_style_reference_path(args.style_reference)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    options = CodexOptions(
        model=args.model,
        executable=args.codex_executable,
        timeout_seconds=args.timeout_seconds,
        reasoning_effort=args.reasoning_effort,
    )
    result = run_docx_rollout(
        args.source,
        args.out_dir,
        options=options,
        style_reference_path=args.style_reference,
    )
    log.info("done. S5U-803 DOCX artifacts under %s", args.out_dir)
    log.info("final QA findings: %d", len(result.qa_final))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
