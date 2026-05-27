"""Shared helpers for the S5U-802 improved calibration rerun."""

from __future__ import annotations

import json
import logging
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (
    REPO_ROOT,
    REPO_ROOT / "apps" / "pipeline" / "src",
    REPO_ROOT / "packages" / "schemas" / "python",
):
    path_text = str(_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from atr_pipeline.services.llm.russian_style_critic import (  # noqa: E402
    CriticPageRequest,
    CriticParagraph,
)

from .qa_checks import QAFinding  # noqa: E402

EVAL_DIR = REPO_ROOT / "tmp" / "translation-eval"
POC_ROOT = EVAL_DIR / "s5u-776-ensemble-poc"
DEFAULT_OUT_DIR = POC_ROOT / "style-v2"
DEFAULT_MODEL = "gpt-5.5"
PARA_SPLIT_RE = re.compile(r"\n\s*\n")
FENCE_RE = re.compile(r"^```(?:[a-zA-Z0-9_-]+)?\s*|\s*```$", re.DOTALL)

log = logging.getLogger("translation_eval.improved_rerun")


@dataclass(frozen=True)
class CodexOptions:
    model: str = DEFAULT_MODEL
    executable: str = "codex"
    timeout_seconds: int = 900
    reasoning_effort: str = "high"
    ignore_user_config: bool = True


@dataclass(frozen=True)
class CallRecord:
    stage: str
    model: str
    wall_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class PageRun:
    page: int
    en_text: str
    old_final: str
    synth_v1: str = ""
    editor_text: str = ""
    final_text: str = ""
    qa_v1: list[QAFinding] = field(default_factory=list)
    qa_editor: list[QAFinding] = field(default_factory=list)
    qa_final: list[QAFinding] = field(default_factory=list)
    critic_findings: int = 0
    repaired_ids: list[str] = field(default_factory=list)
    calls: list[CallRecord] = field(default_factory=list)


def split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in PARA_SPLIT_RE.split(text.strip()) if part.strip()]


def qa_as_json(findings: list[QAFinding]) -> list[dict[str, str]]:
    return [{"code": finding.code, "detail": finding.detail} for finding in findings]


def read_gemma_witness(page: int) -> str:
    path = EVAL_DIR / f"page-{page}-ru-translategemma.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def old_final_path(page: int) -> Path:
    candidates = (
        POC_ROOT / "opus" / f"page-{page}-synth-v2.txt",
        POC_ROOT / "opus" / f"page-{page}-synth-v1.txt",
        POC_ROOT / "codex" / f"page-{page}-synth-v2.txt",
    )
    for path in candidates:
        if path.is_file():
            return path
    msg = f"missing old S5U-776 final for page {page}"
    raise FileNotFoundError(msg)


def validate_out_dir(out_dir: Path) -> None:
    root = POC_ROOT.resolve()
    target = out_dir.resolve()
    if target == root or root not in target.parents:
        msg = (
            "S5U-802 output must be a new subfolder under "
            f"{POC_ROOT.relative_to(REPO_ROOT)}; got {out_dir}"
        )
        raise ValueError(msg)


def call_codex_text(
    prompt: str,
    *,
    stage: str,
    options: CodexOptions,
) -> tuple[str, CallRecord]:
    log.info("calling %s (%s)", stage, options.model)
    with tempfile.TemporaryDirectory(prefix="s5u802-codex-text-") as tmpdir:
        last_message = Path(tmpdir) / "last_message.txt"
        argv = [options.executable, "exec"]
        if options.ignore_user_config:
            argv.append("--ignore-user-config")
        argv.extend(
            [
                "--model",
                options.model,
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--json",
                "--output-last-message",
                str(last_message),
                "-c",
                "approval_policy='never'",
                "-c",
                f"model_reasoning_effort='{options.reasoning_effort}'",
                prompt,
            ]
        )
        t0 = time.perf_counter()
        proc = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=options.timeout_seconds,
            check=False,
        )
        wall = time.perf_counter() - t0
        if proc.returncode != 0:
            msg = f"codex text call failed for {stage}: {proc.stderr[:500]}"
            raise RuntimeError(msg)
        input_tokens, output_tokens = parse_token_usage(proc.stdout)
        return (
            clean_model_text(last_message.read_text(encoding="utf-8")),
            CallRecord(
                stage=stage,
                model=options.model,
                wall_seconds=round(wall, 2),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )


def clean_model_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = FENCE_RE.sub("", cleaned).strip()
    return cleaned


def parse_token_usage(stdout: str) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        input_tokens = _max_int(input_tokens, usage.get("input_tokens"))
        output_tokens = _max_int(output_tokens, usage.get("output_tokens"))
    return input_tokens, output_tokens


def _max_int(current: int, value: object) -> int:
    return max(current, value) if isinstance(value, int) else current


def text_prompt(system_prompt: str, user_message: str) -> str:
    return "\n\n".join(
        [
            "You are running as a non-interactive translation stage.",
            "Do not inspect files. Do not use tools. Return only the requested text.",
            "SYSTEM INSTRUCTIONS:",
            system_prompt,
            "USER PAYLOAD:",
            user_message.rstrip(),
        ]
    )


def build_critic_request(page: int, en_text: str, ru_text: str) -> CriticPageRequest:
    en_paras = split_paragraphs(en_text)
    ru_paras = split_paragraphs(ru_text)
    paragraphs: list[CriticParagraph] = []
    for index, ru_para in enumerate(ru_paras):
        paragraphs.append(
            CriticParagraph(
                paragraph_id=f"p{index + 1:03d}",
                block_type="paragraph",
                ru_text=ru_para,
                source_text=en_paras[index] if index < len(en_paras) else "",
                prev_ru_text=ru_paras[index - 1] if index > 0 else "",
                next_ru_text=ru_paras[index + 1] if index + 1 < len(ru_paras) else "",
            )
        )
    return CriticPageRequest(
        document_id="s5u-776",
        page_id=f"page-{page}",
        paragraphs=paragraphs,
    )


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def adapter_codex_executable(out_dir: Path, options: CodexOptions) -> str:
    if not options.ignore_user_config:
        return options.executable
    wrapper = out_dir / "_codex-ignore-user-config.sh"
    quoted = shlex.quote(options.executable)
    wrapper.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                'if [ "$1" = "exec" ]; then',
                "  shift",
                f'  exec {quoted} exec --ignore-user-config "$@"',
                "fi",
                f'exec {quoted} "$@"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    return str(wrapper)
