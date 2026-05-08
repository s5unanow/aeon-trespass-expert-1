"""S5U-776 ensemble translation POC orchestrator (local-only, EN→RU).

Workflow per page:
  1. Load EN source from ``tmp/translation-eval/page-{N}-en.txt``.
  2. Run three Sonnet variants (literal / literary / idiomatic).
  3. Synthesise via Opus from EN + 3 variants → ``synth_v1``.
  4. Run deterministic QA (refs / placeholders / mechanics / glossary /
     forbidden phrases) on ``synth_v1``.
  5. Read TranslateGemma omission witness from
     ``tmp/translation-eval/page-{N}-ru-translategemma.txt`` (S5U-775
     output) and run a coarse paragraph/character coverage check.
  6. If any findings, send them + ``synth_v1`` to Opus for minimal repair
     → ``synth_v2``. Re-run QA on ``synth_v2``.
  7. Write per-stage artefacts and a summary ``report.md`` /
     ``memory-candidates.md`` to
     ``tmp/translation-eval/s5u-776-ensemble-poc/``.

Run with:
    uv run python scripts/translation_eval/ensemble_poc.py 1 2

The orchestrator imports ``anthropic`` lazily and requires
``ANTHROPIC_API_KEY`` to be set. All artefacts stay under
``tmp/translation-eval/s5u-776-ensemble-poc/`` (gitignored).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .prompts import (
    SONNET_VARIANTS,
    build_opus_repair_system_prompt,
    build_opus_repair_user_message,
    build_opus_synthesis_system_prompt,
    build_opus_synthesis_user_message,
    build_sonnet_system_prompt,
)
from .qa_checks import QAFinding, all_checks
from .report import write_memory_candidates, write_report

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "tmp" / "translation-eval"
OUT_ROOT = EVAL_DIR / "s5u-776-ensemble-poc"

SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096

log = logging.getLogger("translation_eval.ensemble_poc")


@dataclass
class CallRecord:
    stage: str
    model: str
    wall_seconds: float
    input_tokens: int
    output_tokens: int


@dataclass
class PageResult:
    page: int
    sonnet_variants: list[tuple[str, str]] = field(default_factory=list)
    synth_v1: str = ""
    qa_v1: list[QAFinding] = field(default_factory=list)
    gemma_witness: str = ""
    synth_v2: str = ""
    qa_v2: list[QAFinding] = field(default_factory=list)
    calls: list[CallRecord] = field(default_factory=list)


def _format_findings(findings: list[QAFinding]) -> list[str]:
    return [f"{f.code}: {f.detail}" for f in findings]


def _call_anthropic(
    client: Any,
    *,
    stage: str,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
) -> tuple[str, CallRecord]:
    log.info("calling %s (%s) ...", stage, model)
    t0 = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    wall = time.perf_counter() - t0
    text_parts: list[str] = []
    for block in response.content:
        block_type = getattr(block, "type", "")
        if block_type == "text":
            text_parts.append(getattr(block, "text", ""))
    text = "\n".join(text_parts).strip()
    call = CallRecord(
        stage=stage,
        model=model,
        wall_seconds=round(wall, 2),
        input_tokens=int(getattr(response.usage, "input_tokens", 0)),
        output_tokens=int(getattr(response.usage, "output_tokens", 0)),
    )
    log.info(
        "  done in %.1fs  tokens in=%d out=%d",
        wall,
        call.input_tokens,
        call.output_tokens,
    )
    return text, call


def _read_gemma_witness(page: int) -> str:
    path = EVAL_DIR / f"page-{page}-ru-translategemma.txt"
    if not path.is_file():
        log.warning("Gemma witness not found at %s — omission check skipped", path)
        return ""
    return path.read_text(encoding="utf-8")


def _process_page(client: Any, page: int, out_dir: Path) -> PageResult:
    en_path = EVAL_DIR / f"page-{page}-en.txt"
    if not en_path.is_file():
        msg = f"missing source page {en_path}"
        raise FileNotFoundError(msg)

    en_text = en_path.read_text(encoding="utf-8")
    page_dir = out_dir
    inputs_dir = page_dir / "inputs"
    sonnet_dir = page_dir / "sonnet"
    opus_dir = page_dir / "opus"
    qa_dir = page_dir / "qa"
    for d in (inputs_dir, sonnet_dir, opus_dir, qa_dir):
        d.mkdir(parents=True, exist_ok=True)

    (inputs_dir / f"page-{page}-en.txt").write_text(en_text, encoding="utf-8")

    result = PageResult(page=page)

    # 1. Three Sonnet variants.
    for variant in SONNET_VARIANTS:
        system_prompt = build_sonnet_system_prompt(variant)
        ru, call = _call_anthropic(
            client,
            stage=f"sonnet:{variant.name}:page-{page}",
            model=SONNET_MODEL,
            system_prompt=system_prompt,
            user_message=en_text.rstrip(),
            temperature=0.3,
        )
        (sonnet_dir / f"page-{page}-{variant.name}.txt").write_text(ru + "\n", encoding="utf-8")
        result.sonnet_variants.append((variant.name, ru))
        result.calls.append(call)

    # 2. Opus synthesis.
    synth_system = build_opus_synthesis_system_prompt()
    synth_user = build_opus_synthesis_user_message(en_text, result.sonnet_variants)
    synth_v1, synth_call = _call_anthropic(
        client,
        stage=f"opus-synthesis:page-{page}",
        model=OPUS_MODEL,
        system_prompt=synth_system,
        user_message=synth_user,
        temperature=0.2,
    )
    (opus_dir / f"page-{page}-synth-v1.txt").write_text(synth_v1 + "\n", encoding="utf-8")
    result.synth_v1 = synth_v1
    result.calls.append(synth_call)

    # 3. Read TranslateGemma omission witness (from S5U-775 output).
    gemma_ru = _read_gemma_witness(page)
    result.gemma_witness = gemma_ru

    # 4. Automated QA on synth_v1.
    result.qa_v1 = all_checks(en_text, synth_v1, gemma_ru or None)
    (qa_dir / f"page-{page}-qa-v1.json").write_text(
        json.dumps(
            [{"code": f.code, "detail": f.detail} for f in result.qa_v1],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    # 5. Opus minimal repair (only if there are findings).
    if result.qa_v1:
        repair_system = build_opus_repair_system_prompt()
        repair_user = build_opus_repair_user_message(
            en_text, synth_v1, _format_findings(result.qa_v1)
        )
        synth_v2, repair_call = _call_anthropic(
            client,
            stage=f"opus-repair:page-{page}",
            model=OPUS_MODEL,
            system_prompt=repair_system,
            user_message=repair_user,
            temperature=0.0,
        )
        (opus_dir / f"page-{page}-synth-v2.txt").write_text(synth_v2 + "\n", encoding="utf-8")
        result.synth_v2 = synth_v2
        result.calls.append(repair_call)
        result.qa_v2 = all_checks(en_text, synth_v2, gemma_ru or None)
        (qa_dir / f"page-{page}-qa-v2.json").write_text(
            json.dumps(
                [{"code": f.code, "detail": f.detail} for f in result.qa_v2],
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        result.synth_v2 = synth_v1
        result.qa_v2 = []

    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pages",
        nargs="+",
        type=int,
        choices=[1, 2],
        help="Page numbers to process (1 and/or 2)",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write(
            "ANTHROPIC_API_KEY is not set. Refusing to run — the orchestrator "
            "needs Anthropic API access for Sonnet variants and Opus synthesis.\n"
        )
        return 2

    try:
        from anthropic import Anthropic
    except ImportError:
        sys.stderr.write(
            "anthropic package not available. Run via `uv run` from the "
            "repo root so the apps/pipeline dependency is on the path.\n"
        )
        return 2

    client = Anthropic()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    results: list[PageResult] = []
    for page in sorted(set(args.pages)):
        log.info("=== page %d ===", page)
        results.append(_process_page(client, page, OUT_ROOT))

    write_report(results, OUT_ROOT)
    write_memory_candidates(results, OUT_ROOT)

    log.info("done. artefacts under %s", OUT_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
