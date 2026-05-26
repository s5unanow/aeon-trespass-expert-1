"""S5U-776 ensemble translation POC orchestrator (local-only, EN→RU).

Workflow per page:
  1. Load EN source from ``tmp/translation-eval/page-{N}-en.txt``.
  2. Run three AGY variants (literal / literary / idiomatic).
  3. Synthesise via Opus from EN + 3 variants → ``synth_v1``.
  4. Run deterministic QA (refs / placeholders / mechanics / glossary /
     forbidden phrases) on ``synth_v1``.
  5. Read TranslateGemma omission witness from
     ``tmp/translation-eval/page-{N}-ru-translategemma.txt`` (S5U-775
     output) and run a coarse paragraph/character coverage check.
  6. Send findings + ``synth_v1`` to Opus for a final literary editor pass
     → ``synth_v2``. Re-run QA on ``synth_v2``.
  7. Write per-stage artefacts and a summary ``report.md`` /
     ``memory-candidates.md`` to
     ``tmp/translation-eval/s5u-776-ensemble-poc/``.

Run with:
    uv run python -m scripts.translation_eval.ensemble_poc 1 2

The orchestrator imports ``anthropic`` lazily for Opus synthesis/repair and
requires ``ANTHROPIC_API_KEY`` to be set. The variant stage shells out to
``agy --print``; AGY CLI v1 exposes no non-interactive model selector, so
the runner records/requests the desired Pro/high profile in prompts and
uses the user's current Antigravity CLI configuration. All artefacts stay under
``tmp/translation-eval/s5u-776-ensemble-poc/`` (gitignored).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.translation_eval.prompts import (
        TRANSLATION_VARIANTS,
        build_opus_repair_system_prompt,
        build_opus_repair_user_message,
        build_opus_synthesis_system_prompt,
        build_opus_synthesis_user_message,
        build_variant_system_prompt,
    )
    from scripts.translation_eval.qa_checks import QAFinding, all_checks
    from scripts.translation_eval.report import write_memory_candidates, write_report
else:
    from .prompts import (
        TRANSLATION_VARIANTS,
        build_opus_repair_system_prompt,
        build_opus_repair_user_message,
        build_opus_synthesis_system_prompt,
        build_opus_synthesis_user_message,
        build_variant_system_prompt,
    )
    from .qa_checks import QAFinding, all_checks
    from .report import write_memory_candidates, write_report

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "tmp" / "translation-eval"
OUT_ROOT = EVAL_DIR / "s5u-776-ensemble-poc"

AGY_MODEL_PROFILE = "gemini-pro-high"
DEFAULT_OPUS_MODEL = "claude-opus-4-20250514"
MAX_TOKENS = 4096
AGY_DEFAULT_TIMEOUT = "15m"
_DURATION_PART_RE = re.compile(r"(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$")
_AGY_ERROR_PREFIXES = ("error:", "fatal:")

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
    variants: list[tuple[str, str]] = field(default_factory=list)
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


def _build_agy_prompt(system_prompt: str, user_message: str) -> str:
    """Combine the variant system prompt and source text for ``agy --print``."""
    return "\n\n".join(
        [
            system_prompt,
            "AGY model profile requested by the pipeline: Pro model with high effort. "
            "Use that profile if your current Antigravity CLI session supports it.",
            "--- Source text to translate ---",
            user_message.rstrip(),
            "--- Output contract ---",
            "Output only the Russian translation. Do not include commentary.",
        ]
    )


def _build_agy_argv(
    *,
    executable: str,
    prompt: str,
    timeout: str,
) -> list[str]:
    """Build the current AGY v1 non-interactive argv.

    Local ``agy --help`` exposes ``--print`` and ``--print-timeout`` but no
    model/effort flags. Keep this isolated so future AGY model-selection flags
    can be added in one place.
    """
    return [executable, "--print-timeout", timeout, "--print", prompt]


def _looks_like_agy_error(text: str) -> bool:
    """AGY can report internal failures on stdout while exiting 0."""
    normalized = text.strip().lower()
    return normalized.startswith(_AGY_ERROR_PREFIXES) or "timed out waiting" in normalized


def _call_agy(
    *,
    stage: str,
    system_prompt: str,
    user_message: str,
    executable: str,
    timeout: str,
) -> tuple[str, CallRecord]:
    log.info("calling %s (%s via %s) ...", stage, AGY_MODEL_PROFILE, executable)
    prompt = _build_agy_prompt(system_prompt, user_message)
    argv = _build_agy_argv(executable=executable, prompt=prompt, timeout=timeout)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_duration_to_seconds(timeout),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"AGY CLI timed out after {timeout}"
        raise RuntimeError(msg) from exc
    except FileNotFoundError as exc:
        msg = f"AGY CLI not found (executable={executable!r})"
        raise RuntimeError(msg) from exc

    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        stderr = proc.stderr[:500] if proc.stderr else "(no stderr)"
        msg = f"AGY CLI exited with code {proc.returncode}: {stderr}"
        raise RuntimeError(msg)

    text = proc.stdout.strip()
    if not text:
        msg = "AGY CLI returned empty output"
        raise RuntimeError(msg)
    if _looks_like_agy_error(text) or (proc.stderr and _looks_like_agy_error(proc.stderr)):
        msg = f"AGY CLI reported an error: {(text or proc.stderr).strip()[:500]}"
        raise RuntimeError(msg)

    call = CallRecord(
        stage=stage,
        model=AGY_MODEL_PROFILE,
        wall_seconds=round(wall, 2),
        input_tokens=0,
        output_tokens=0,
    )
    log.info("  done in %.1fs", wall)
    return text, call


def _duration_to_seconds(raw: str) -> int:
    """Parse AGY-style duration strings such as ``15m`` / ``5m0s`` / ``900s``."""
    value = raw.strip().lower()
    if value.isdigit():
        return int(value)
    match = _DURATION_PART_RE.fullmatch(value)
    if not match:
        msg = f"unsupported duration: {raw!r}"
        raise ValueError(msg)
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m") or 0)
    seconds = int(match.group("s") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        msg = f"duration must be positive: {raw!r}"
        raise ValueError(msg)
    return total


def _read_gemma_witness(page: int) -> str:
    path = EVAL_DIR / f"page-{page}-ru-translategemma.txt"
    if not path.is_file():
        log.warning("Gemma witness not found at %s — omission check skipped", path)
        return ""
    return path.read_text(encoding="utf-8")


def _process_page(
    client: Any,
    page: int,
    out_dir: Path,
    *,
    agy_executable: str,
    agy_timeout: str,
    opus_model: str,
) -> PageResult:
    en_path = EVAL_DIR / f"page-{page}-en.txt"
    if not en_path.is_file():
        msg = f"missing source page {en_path}"
        raise FileNotFoundError(msg)

    en_text = en_path.read_text(encoding="utf-8")
    page_dir = out_dir
    inputs_dir = page_dir / "inputs"
    variant_dir = page_dir / "agy"
    opus_dir = page_dir / "opus"
    qa_dir = page_dir / "qa"
    for d in (inputs_dir, variant_dir, opus_dir, qa_dir):
        d.mkdir(parents=True, exist_ok=True)

    (inputs_dir / f"page-{page}-en.txt").write_text(en_text, encoding="utf-8")

    result = PageResult(page=page)

    # 1. Three AGY variants.
    for variant in TRANSLATION_VARIANTS:
        system_prompt = build_variant_system_prompt(variant)
        ru, call = _call_agy(
            stage=f"agy:{variant.name}:page-{page}",
            system_prompt=system_prompt,
            user_message=en_text.rstrip(),
            executable=agy_executable,
            timeout=agy_timeout,
        )
        (variant_dir / f"page-{page}-{variant.name}.txt").write_text(
            ru + "\n",
            encoding="utf-8",
        )
        result.variants.append((variant.name, ru))
        result.calls.append(call)

    # 2. Opus synthesis.
    synth_system = build_opus_synthesis_system_prompt()
    synth_user = build_opus_synthesis_user_message(en_text, result.variants)
    synth_v1, synth_call = _call_anthropic(
        client,
        stage=f"opus-synthesis:page-{page}",
        model=opus_model,
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

    # 5. Opus final editor pass. Run even when deterministic QA is clean:
    # stylistic failures like literal calques are exactly what deterministic
    # QA historically missed.
    repair_system = build_opus_repair_system_prompt()
    repair_user = build_opus_repair_user_message(
        en_text,
        synth_v1,
        _format_findings(result.qa_v1),
    )
    synth_v2, repair_call = _call_anthropic(
        client,
        stage=f"opus-editor:page-{page}",
        model=opus_model,
        system_prompt=repair_system,
        user_message=repair_user,
        temperature=0.1,
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
    parser.add_argument(
        "--agy-executable",
        default=os.environ.get("ATR_AGY_EXECUTABLE", "agy"),
        help="AGY CLI executable to use for the variant stage (default: agy)",
    )
    parser.add_argument(
        "--agy-timeout",
        default=os.environ.get("ATR_AGY_PRINT_TIMEOUT", AGY_DEFAULT_TIMEOUT),
        help="AGY print timeout duration, e.g. 15m or 900s",
    )
    parser.add_argument(
        "--opus-model",
        default=os.environ.get("ANTHROPIC_OPUS_MODEL", DEFAULT_OPUS_MODEL),
        help="Anthropic Opus model for synthesis/final editing",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write(
            "ANTHROPIC_API_KEY is not set. Refusing to run — the orchestrator "
            "needs Anthropic API access for Opus synthesis/final editing.\n"
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
        results.append(
            _process_page(
                client,
                page,
                OUT_ROOT,
                agy_executable=args.agy_executable,
                agy_timeout=args.agy_timeout,
                opus_model=args.opus_model,
            )
        )

    write_report(results, OUT_ROOT)
    write_memory_candidates(results, OUT_ROOT)

    log.info("done. artefacts under %s", OUT_ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
