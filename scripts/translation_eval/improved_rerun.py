"""S5U-802 improved S5U-776 calibration rerun.

Local-only runner for the follow-up calibration pass described in S5U-802.
It keeps the original S5U-776 artifacts intact and writes a fresh subfolder
under ``tmp/translation-eval/s5u-776-ensemble-poc/``.

Run from repo root:
    uv run python -m scripts.translation_eval.improved_rerun 1 2
"""

from __future__ import annotations

import argparse
import difflib
import logging
import time
from collections import defaultdict
from pathlib import Path

from atr_pipeline.services.llm.russian_style_critic import CriticPageRequest
from atr_pipeline.services.llm.russian_style_critic_codex import (
    CodexRussianStyleCritic,
)
from atr_pipeline.services.llm.russian_style_repair import (
    RepairPageRequest,
    RepairParagraph,
    repair_paragraph_from_critic,
)
from atr_pipeline.services.llm.russian_style_repair_codex import (
    CodexRussianStyleRepair,
)
from atr_schemas.translation_style_critic_v1 import TranslationStyleCriticFindingV1
from atr_schemas.translation_style_repair_v1 import (
    TranslationStyleRepairChangeV1,
    TranslationStyleRepairPageV1,
)

from .improved_rerun_core import (
    DEFAULT_MODEL,
    DEFAULT_OUT_DIR,
    EVAL_DIR,
    CallRecord,
    CodexOptions,
    PageRun,
    adapter_codex_executable,
    build_critic_request,
    call_codex_text,
    old_final_path,
    qa_as_json,
    read_gemma_witness,
    split_paragraphs,
    text_prompt,
    validate_out_dir,
    write_json,
)
from .improved_rerun_report import write_comparison, write_report
from .prompts import (
    TRANSLATION_VARIANTS,
    build_opus_repair_system_prompt,
    build_opus_repair_user_message,
    build_opus_synthesis_system_prompt,
    build_opus_synthesis_user_message,
    build_variant_system_prompt,
)
from .qa_checks import QAFinding, all_checks, find_style_red_flags

log = logging.getLogger("translation_eval.improved_rerun")


def run_page(
    page: int,
    out_dir: Path,
    *,
    options: CodexOptions,
) -> PageRun:
    en_text = (EVAL_DIR / f"page-{page}-en.txt").read_text(encoding="utf-8")
    old_final = old_final_path(page).read_text(encoding="utf-8")
    gemma = read_gemma_witness(page)
    result = PageRun(page=page, en_text=en_text, old_final=old_final)

    (out_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (out_dir / "inputs" / f"page-{page}-en.txt").write_text(en_text, encoding="utf-8")

    variants = run_variants(
        page,
        en_text,
        out_dir,
        options=options,
        calls=result.calls,
    )
    result.synth_v1 = run_synthesis(
        page,
        en_text,
        variants,
        out_dir,
        options=options,
        calls=result.calls,
    )
    result.qa_v1 = all_checks(en_text, result.synth_v1, gemma or None)
    write_json(out_dir / "qa" / f"page-{page}-qa-v1.json", qa_as_json(result.qa_v1))

    result.editor_text = run_editor(
        page,
        en_text,
        result.synth_v1,
        result.qa_v1,
        out_dir,
        options=options,
        calls=result.calls,
    )
    result.qa_editor = all_checks(en_text, result.editor_text, gemma or None)
    write_json(
        out_dir / "qa" / f"page-{page}-qa-editor.json",
        qa_as_json(result.qa_editor),
    )

    critic_request = build_critic_request(page, en_text, result.editor_text)
    adapter_executable = adapter_codex_executable(out_dir, options)
    critic = CodexRussianStyleCritic(
        model=options.model,
        timeout_seconds=options.timeout_seconds,
        reasoning_effort=options.reasoning_effort,
        executable=adapter_executable,
    )
    t0 = time.perf_counter()
    critic_response = critic.critique_page(critic_request)
    result.calls.append(
        CallRecord(
            stage=f"codex-style-critic:page-{page}",
            model=options.model,
            wall_seconds=round(time.perf_counter() - t0, 2),
            input_tokens=critic_response.meta.input_tokens,
            output_tokens=critic_response.meta.output_tokens,
        )
    )
    result.critic_findings = len(critic_response.result.findings)
    write_json(out_dir / "critic" / f"page-{page}-critic.json", critic_response.result)

    report = run_repair(
        page,
        result,
        critic_request,
        critic_response.result.findings,
        out_dir,
        options=options,
        adapter_executable=adapter_executable,
    )
    result.repaired_ids = report.repaired_paragraph_ids
    write_json(out_dir / "qa" / f"page-{page}-qa-final.json", qa_as_json(result.qa_final))
    return result


def run_variants(
    page: int,
    en_text: str,
    out_dir: Path,
    *,
    options: CodexOptions,
    calls: list[CallRecord],
) -> list[tuple[str, str]]:
    variants: list[tuple[str, str]] = []
    for variant in TRANSLATION_VARIANTS:
        text, call = call_codex_text(
            text_prompt(build_variant_system_prompt(variant), en_text),
            stage=f"codex-variant:{variant.name}:page-{page}",
            options=options,
        )
        variant_path = out_dir / "variants" / f"page-{page}-{variant.name}.txt"
        variant_path.parent.mkdir(parents=True, exist_ok=True)
        variant_path.write_text(text + "\n", encoding="utf-8")
        variants.append((variant.name, text))
        calls.append(call)
    return variants


def run_synthesis(
    page: int,
    en_text: str,
    variants: list[tuple[str, str]],
    out_dir: Path,
    *,
    options: CodexOptions,
    calls: list[CallRecord],
) -> str:
    user_message = build_opus_synthesis_user_message(en_text, variants)
    text, call = call_codex_text(
        text_prompt(build_opus_synthesis_system_prompt(), user_message),
        stage=f"codex-synthesis:page-{page}",
        options=options,
    )
    calls.append(call)
    (out_dir / "synthesis").mkdir(parents=True, exist_ok=True)
    (out_dir / "synthesis" / f"page-{page}-synth-v1.txt").write_text(
        text + "\n",
        encoding="utf-8",
    )
    return text


def run_editor(
    page: int,
    en_text: str,
    synth_v1: str,
    findings: list[QAFinding],
    out_dir: Path,
    *,
    options: CodexOptions,
    calls: list[CallRecord],
) -> str:
    user_message = build_opus_repair_user_message(
        en_text,
        synth_v1,
        [f"{f.code}: {f.detail}" for f in findings],
    )
    text, call = call_codex_text(
        text_prompt(build_opus_repair_system_prompt(), user_message),
        stage=f"codex-editor:page-{page}",
        options=options,
    )
    calls.append(call)
    (out_dir / "editor").mkdir(parents=True, exist_ok=True)
    (out_dir / "editor" / f"page-{page}-editor.txt").write_text(
        text + "\n",
        encoding="utf-8",
    )
    return text


def run_repair(
    page: int,
    result: PageRun,
    critic_request: CriticPageRequest,
    findings: list[TranslationStyleCriticFindingV1],
    out_dir: Path,
    *,
    options: CodexOptions,
    adapter_executable: str,
) -> TranslationStyleRepairPageV1:
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
        repair_response = repair.repair_page(repair_request)
        result.calls.append(
            CallRecord(
                stage=f"codex-style-repair:page-{page}",
                model=options.model,
                wall_seconds=round(time.perf_counter() - t0, 2),
                input_tokens=repair_response.meta.input_tokens,
                output_tokens=repair_response.meta.output_tokens,
            )
        )
        repairs = {item.paragraph_id: item.repaired_text for item in repair_response.result.repairs}

    changes = apply_text_repairs(result, repair_request, repairs)
    result.qa_final = all_checks(
        result.en_text,
        result.final_text,
        read_gemma_witness(page) or None,
    )
    report = build_repair_report(repair_request, findings, changes, result)
    write_json(out_dir / "repair" / f"page-{page}-repair-report.json", report)
    final_path = out_dir / "final" / f"page-{page}-ru-final.txt"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(result.final_text + "\n", encoding="utf-8")
    return report


def build_repair_request(
    critic_request: CriticPageRequest,
    findings: list[TranslationStyleCriticFindingV1],
) -> RepairPageRequest:
    findings_by_id: dict[str, list[TranslationStyleCriticFindingV1]] = defaultdict(list)
    for finding in findings:
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


def apply_text_repairs(
    result: PageRun,
    repair_request: RepairPageRequest,
    repairs: dict[str, str],
) -> list[TranslationStyleRepairChangeV1]:
    final_paras = split_paragraphs(result.editor_text)
    changes: list[TranslationStyleRepairChangeV1] = []
    for paragraph in repair_request.paragraphs:
        after = repairs.get(paragraph.paragraph_id)
        if not after or after == paragraph.current_text:
            continue
        idx = int(paragraph.paragraph_id[1:]) - 1
        final_paras[idx] = after
        changes.append(make_change(paragraph, after))
    result.final_text = "\n\n".join(final_paras)
    return changes


def make_change(paragraph: RepairParagraph, after: str) -> TranslationStyleRepairChangeV1:
    return TranslationStyleRepairChangeV1(
        paragraph_id=paragraph.paragraph_id,
        block_type=paragraph.block_type,
        before_text=paragraph.current_text,
        after_text=after,
        finding_quotes=[finding.quote for finding in paragraph.findings],
        diff=list(
            difflib.unified_diff(
                [paragraph.current_text],
                [after],
                fromfile="before",
                tofile="after",
                lineterm="",
            )
        ),
    )


def build_repair_report(
    repair_request: RepairPageRequest,
    findings: list[TranslationStyleCriticFindingV1],
    changes: list[TranslationStyleRepairChangeV1],
    result: PageRun,
) -> TranslationStyleRepairPageV1:
    changed_ids = {change.paragraph_id for change in changes}
    return TranslationStyleRepairPageV1(
        document_id=repair_request.document_id,
        page_id=repair_request.page_id,
        source_critic_findings_count=len(findings),
        repaired_paragraph_ids=[
            p.paragraph_id for p in repair_request.paragraphs if p.paragraph_id in changed_ids
        ],
        skipped_paragraph_ids=[
            p.paragraph_id for p in repair_request.paragraphs if p.paragraph_id not in changed_ids
        ],
        changes=changes,
        post_repair_translation_qa_count=len(result.qa_final),
        post_repair_style_qa_count=len(find_style_red_flags(result.final_text)),
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages", nargs="+", type=int, choices=[1, 2])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--reasoning-effort", default="high")
    args = parser.parse_args(argv)

    validate_out_dir(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    options = CodexOptions(
        model=args.model,
        executable=args.codex_executable,
        timeout_seconds=args.timeout_seconds,
        reasoning_effort=args.reasoning_effort,
    )
    results = [
        run_page(
            page,
            args.out_dir,
            options=options,
        )
        for page in sorted(set(args.pages))
    ]
    write_report(results, args.out_dir, options.model, options.reasoning_effort)
    write_comparison(results, args.out_dir)
    log.info("done. S5U-802 artifacts under %s", args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
