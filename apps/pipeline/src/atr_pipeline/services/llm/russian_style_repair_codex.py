"""Codex CLI adapter for targeted Russian paragraph style repair."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Final

from atr_pipeline.services.llm.russian_style_repair import (
    RepairPageDraft,
    RepairPageRequest,
    RussianStyleRepairMeta,
    RussianStyleRepairResponse,
    build_repair_prompt,
)

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS: Final[int] = 600
_ERROR_SNIPPET_BUDGET: Final[int] = 500
_ALLOWED_SANDBOX: Final[frozenset[str]] = frozenset(
    {"read-only", "workspace-write", "danger-full-access"},
)
_ALLOWED_APPROVAL_POLICY: Final[frozenset[str]] = frozenset({"never"})
_FENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```",
    re.DOTALL,
)


def _bounded(text: str | None) -> str:
    if not text:
        return "(empty)"
    return text[:_ERROR_SNIPPET_BUDGET]


def _parse_last_message(raw: str) -> dict[str, object]:
    text = raw.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"Codex style repair output is not valid JSON: {_bounded(text[:200])}"
        raise RuntimeError(msg) from exc
    if not isinstance(data, dict):
        msg = f"Codex style repair output is not a JSON object: {type(data).__name__}"
        raise RuntimeError(msg)
    return data


def _parse_event_stream_for_tokens(stdout: str) -> tuple[int, int, int]:
    input_tokens = 0
    output_tokens = 0
    event_count = 0
    for line in stdout.splitlines():
        try:
            event: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_count += 1
        usage = event.get("usage") or event.get("token_usage")
        if not isinstance(usage, dict):
            continue
        it = usage.get("input_tokens") or usage.get("prompt_tokens")
        ot = usage.get("output_tokens") or usage.get("completion_tokens")
        if isinstance(it, int):
            input_tokens = max(input_tokens, it)
        if isinstance(ot, int):
            output_tokens = max(output_tokens, ot)
    return input_tokens, output_tokens, event_count


class CodexRussianStyleRepair:
    """Targeted Russian style repair backed by local ``codex exec``."""

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        reasoning_effort: str = "high",
        sandbox: str = "read-only",
        approval_policy: str = "never",
        executable: str | None = None,
        json_events: bool = True,
    ) -> None:
        if not model:
            msg = "Codex Russian style repair requires a non-empty model."
            raise ValueError(msg)
        if sandbox not in _ALLOWED_SANDBOX:
            msg = f"Unsupported Codex sandbox {sandbox!r}."
            raise ValueError(msg)
        if approval_policy not in _ALLOWED_APPROVAL_POLICY:
            msg = f"Unsupported Codex approval_policy {approval_policy!r}."
            raise ValueError(msg)
        self._model = model
        self._timeout = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._sandbox = sandbox
        self._approval_policy = approval_policy
        self._executable = executable or "codex"
        self._json_events = json_events

    def repair_page(self, request: RepairPageRequest) -> RussianStyleRepairResponse:
        log.info(
            "Codex style repair: model=%s page=%s paragraphs=%d effort=%s",
            self._model,
            request.page_id,
            len(request.paragraphs),
            self._reasoning_effort,
        )
        with tempfile.TemporaryDirectory(prefix="codex-style-repair-") as tmpdir:
            return self._repair_in_tmpdir(request, Path(tmpdir))

    def _repair_in_tmpdir(
        self,
        request: RepairPageRequest,
        tmp_path: Path,
    ) -> RussianStyleRepairResponse:
        schema_path = tmp_path / "style_repair.schema.json"
        last_msg_path = tmp_path / "last_message.txt"
        schema_path.write_text(
            json.dumps(RepairPageDraft.model_json_schema(), ensure_ascii=False),
            encoding="utf-8",
        )
        argv = self._build_argv(
            prompt=build_repair_prompt(request),
            schema_path=schema_path,
            last_msg_path=last_msg_path,
        )
        proc = self._run(argv)
        if proc.returncode != 0:
            msg = f"Codex style repair exited with code {proc.returncode}: {_bounded(proc.stderr)}"
            raise RuntimeError(msg)
        last_msg = last_msg_path.read_text(encoding="utf-8")
        if not last_msg.strip():
            msg = "Codex style repair produced no final message"
            raise RuntimeError(msg)
        result = RepairPageDraft.model_validate(_parse_last_message(last_msg))
        self._validate_result(request, result)
        return self._response(result, last_msg, proc.stdout)

    def _validate_result(self, request: RepairPageRequest, result: RepairPageDraft) -> None:
        if result.document_id != request.document_id or result.page_id != request.page_id:
            msg = (
                "Codex style repair returned mismatched document/page: "
                f"{result.document_id}/{result.page_id}"
            )
            raise RuntimeError(msg)
        requested_ids = {paragraph.paragraph_id for paragraph in request.paragraphs}
        unknown = [
            repair.paragraph_id
            for repair in result.repairs
            if repair.paragraph_id not in requested_ids
        ]
        if unknown:
            msg = f"Codex style repair returned unrequested paragraph IDs: {unknown}"
            raise RuntimeError(msg)

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            msg = f"Codex style repair timed out after {self._timeout}s"
            raise RuntimeError(msg) from exc
        except FileNotFoundError as exc:
            msg = f"codex CLI not found (executable={self._executable!r})"
            raise RuntimeError(msg) from exc

    def _response(
        self,
        result: RepairPageDraft,
        last_msg: str,
        stdout: str,
    ) -> RussianStyleRepairResponse:
        input_tokens, output_tokens, event_count = (
            _parse_event_stream_for_tokens(stdout) if self._json_events else (0, 0, 0)
        )
        return RussianStyleRepairResponse(
            result=result,
            meta=RussianStyleRepairMeta(
                provider="codex-cli",
                model=self._model,
                raw_response=last_msg,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                extra={
                    "reasoning_effort": self._reasoning_effort,
                    "sandbox": self._sandbox,
                    "approval_policy": self._approval_policy,
                    "event_count": event_count,
                    "executable": self._executable,
                },
            ),
        )

    def _build_argv(
        self,
        *,
        prompt: str,
        schema_path: Path,
        last_msg_path: Path,
    ) -> list[str]:
        argv = [
            self._executable,
            "exec",
            "--model",
            self._model,
            "--sandbox",
            self._sandbox,
            "--skip-git-repo-check",
            "--color",
            "never",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(last_msg_path),
        ]
        if self._json_events:
            argv.append("--json")
        argv.extend(["-c", f"approval_policy={self._approval_policy!r}"])
        argv.extend(["-c", f"model_reasoning_effort={self._reasoning_effort!r}"])
        argv.append(prompt)
        return argv
