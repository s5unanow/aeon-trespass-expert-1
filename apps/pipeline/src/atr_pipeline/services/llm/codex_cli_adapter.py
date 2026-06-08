"""Codex CLI provider adapter — translation via local ``codex exec``.

Shells out to ``codex exec`` non-interactively with a structured-output
schema and a per-call temp directory for the output capture. The agent's
final message is written to ``--output-last-message <file>`` and parsed
through :class:`TranslationResultV1`. Stdout JSONL events (``--json``) are
parsed best-effort for token-usage metadata only — the authoritative
final-answer source is the message file, never stdout.

Design notes (S5U-747):

- Argv is always a list passed to ``subprocess.run`` with ``shell=False``
  (the default). Never ``shell=True``; never an interpolated shell string.
- Canonical flag forms: ``codex exec`` (not ``codex e``), ``--model`` (not
  ``-m``), ``--sandbox`` (not ``-s``). Tests assert on the literal argv.
- Approval policy is set via ``-c approval_policy=<value>`` because
  ``codex exec`` itself does not expose ``--ask-for-approval``. The
  pipeline allowlist is ``{"never"}`` only — anything else is interactive
  and unsafe for non-interactive runs.
- Sandbox allowlist mirrors the upstream ``[possible values: read-only,
  workspace-write, danger-full-access]`` list.
- ``--dangerously-bypass-approvals-and-sandbox`` is NEVER emitted.
- The output schema is generated in-process from the same builder used by
  the API/Gemini adapters, written into a per-call ``tempfile.Temporary
  Directory()``, and passed via ``--output-schema``. This avoids any
  config-driven path traversal.
- Error messages are bounded (≤500 chars) so source text and stderr leaks
  stay manageable.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Final

from atr_pipeline.services.llm.base import TranslationResponse, TranslationResponseMeta
from atr_pipeline.services.llm.prompt_builder import (
    build_few_shot_examples,
    build_response_schema,
    build_system_prompt,
    build_user_message,
)
from atr_schemas.concept_registry_v1 import ConceptRegistryV1
from atr_schemas.translation_batch_v1 import TranslationBatchV1
from atr_schemas.translation_result_v1 import TranslationResultV1

log = logging.getLogger(__name__)

# Default subprocess timeout (seconds). Codex with high reasoning effort and
# a 24-segment batch can take several minutes per page.
_DEFAULT_TIMEOUT_SECONDS: Final[int] = 600

# Sandbox values the upstream tool documents in `--sandbox` `[possible values: ...]`.
# Anything else is rejected at adapter-construction time.
_ALLOWED_SANDBOX: Final[frozenset[str]] = frozenset(
    {"read-only", "workspace-write", "danger-full-access"},
)

# Approval policy values safe for non-interactive pipeline use. ``never``
# means Codex never prompts the user — the only acceptable value when there
# is no interactive operator. Any other value (``on-failure``,
# ``on-request``, ``always``) is interactive and rejected here.
_ALLOWED_APPROVAL_POLICY: Final[frozenset[str]] = frozenset({"never"})

# Bound on stderr/stdout snippets included in error messages, so source-text
# leaks and verbose tracebacks stay manageable.
_ERROR_SNIPPET_BUDGET: Final[int] = 500

# Markdown-fenced-JSON extractor — reasoning models occasionally wrap output
# in ```json ... ``` even when an output schema is set. One fence-strip
# attempt is fine; deeper recovery is rejected as malformed output.
_FENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```",
    re.DOTALL,
)


def _bounded(text: str | None) -> str:
    """Trim *text* to the error-snippet budget for log/error inclusion."""
    if not text:
        return "(empty)"
    return text[:_ERROR_SNIPPET_BUDGET]


def _parse_last_message(raw: str) -> dict[str, object]:
    """Parse the agent's final message into a translation-result dict.

    Strict — one fence-strip attempt, then ``json.loads``. Anything else is
    a hard reject. The output schema is enforced upstream (Codex sees it via
    ``--output-schema``), so by the time we get here the value should
    already be a JSON object; the fence-strip is a tolerance for reasoning
    models that wrap their answer in a code fence.
    """
    text = raw.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"Codex CLI output is not valid JSON: {_bounded(text[:200])}"
        raise RuntimeError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Codex CLI output is not a JSON object: {type(data).__name__}"
        raise RuntimeError(msg)
    return data


def _parse_event_stream_for_tokens(stdout: str) -> tuple[int, int, int]:
    """Best-effort scan of ``--json`` stdout for token-usage metadata.

    Returns ``(input_tokens, output_tokens, event_count)``. Unknown event
    shapes leave token counts at 0 — the metadata is opportunistic, not
    load-bearing.
    """
    input_tokens = 0
    output_tokens = 0
    event_count = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_count += 1
        # Common shapes — Codex event stream uses different keys across
        # versions. Walk a couple of well-known paths; ignore the rest.
        usage = event.get("usage") or event.get("token_usage")
        if isinstance(usage, dict):
            it = usage.get("input_tokens") or usage.get("prompt_tokens")
            ot = usage.get("output_tokens") or usage.get("completion_tokens")
            if isinstance(it, int):
                input_tokens = max(input_tokens, it)
            if isinstance(ot, int):
                output_tokens = max(output_tokens, ot)
    return input_tokens, output_tokens, event_count


class CodexCLIAdapter:
    """Translate batches via the local ``codex exec`` CLI.

    The adapter constructs an argv list for ``codex exec``, writes a JSON
    Schema file and a final-message file under a per-call temp directory,
    invokes the subprocess with bounded ``timeout_seconds``, parses the
    final message file, and returns a :class:`TranslationResponse` with
    audit-relevant metadata.
    """

    def __init__(  # noqa: PLR0913 — provider config surface; see CLIProviderOptions
        self,
        *,
        model: str,
        concept_registry: ConceptRegistryV1 | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        reasoning_effort: str = "high",
        sandbox: str = "read-only",
        approval_policy: str = "never",
        executable: str | None = None,
        json_events: bool = True,
    ) -> None:
        if sandbox not in _ALLOWED_SANDBOX:
            msg = (
                f"Codex CLI sandbox value {sandbox!r} is not in the allowed "
                f"set {sorted(_ALLOWED_SANDBOX)}. The adapter refuses to "
                f"invoke codex with an unrecognised sandbox mode."
            )
            raise ValueError(msg)
        if approval_policy not in _ALLOWED_APPROVAL_POLICY:
            msg = (
                f"Codex CLI approval_policy {approval_policy!r} is not safe "
                f"for non-interactive pipeline use. Allowed: "
                f"{sorted(_ALLOWED_APPROVAL_POLICY)}."
            )
            raise ValueError(msg)
        if not model:
            msg = "Codex CLI adapter requires a non-empty model name."
            raise ValueError(msg)

        self._model = model
        self._concept_registry = concept_registry
        self._timeout = timeout_seconds
        self._reasoning_effort = reasoning_effort
        self._sandbox = sandbox
        self._approval_policy = approval_policy
        self._executable = executable or "codex"
        self._json_events = json_events

    def _build_prompt(self, batch: TranslationBatchV1) -> str:
        """Combine system prompt, schema, examples, and user message.

        Mirrors :class:`GeminiCLIAdapter._build_prompt` so the prompt
        contract stays adapter-agnostic. The `--output-schema` flag also
        gets the same JSON Schema, so Codex sees a hard structured-output
        constraint *and* a soft schema reminder in the prompt.
        """
        system_prompt = build_system_prompt(
            batch,
            concept_registry=self._concept_registry,
        )
        user_message = build_user_message(batch)
        response_schema = build_response_schema()
        examples = build_few_shot_examples()

        parts = [
            system_prompt,
            "\n\nYou MUST respond with valid JSON matching this schema:\n",
            json.dumps(response_schema, indent=2),
            "\n\n",
        ]
        for i, ex in enumerate(examples, 1):
            parts.append(
                f"--- Example {i} ---\nInput:\n{ex['user']}\n\nOutput:\n{ex['assistant']}\n\n"
            )
        parts.append(f"--- Your task ---\nInput:\n{user_message}\n\nOutput:\n")
        return "".join(parts)

    def _build_argv(
        self,
        *,
        prompt: str,
        model: str,
        schema_path: Path,
        last_msg_path: Path,
    ) -> list[str]:
        """Construct the canonical ``codex exec ...`` argv list.

        The order of options is canonical (long-flag forms throughout) and
        is asserted against in unit tests. ``-c`` config overrides come
        last among options to keep the prompt strictly positional at the
        end.
        """
        argv: list[str] = [
            self._executable,
            "exec",
            "--model",
            model,
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
        # `-c approval_policy=never` — approval_policy is a top-level config
        # key in Codex's config.toml, set as a TOML literal via -c.
        argv.extend(["-c", f"approval_policy={self._approval_policy!r}"])
        # Reasoning effort is also a top-level config key.
        argv.extend(
            [
                "-c",
                f"model_reasoning_effort={self._reasoning_effort!r}",
            ]
        )
        # Prompt is the trailing positional argument (PROMPT in `codex exec
        # [OPTIONS] [PROMPT]`).
        argv.append(prompt)
        return argv

    def translate_batch(
        self,
        batch: TranslationBatchV1,
        model_profile: str = "",
    ) -> TranslationResponse:
        """Translate a batch of segments via ``codex exec``."""
        model = model_profile or self._model
        prompt = self._build_prompt(batch)
        response_schema = build_response_schema()

        log.info(
            "Codex CLI translate_batch: model=%s segments=%d "
            "reasoning_effort=%s sandbox=%s approval_policy=%s",
            model,
            len(batch.segments),
            self._reasoning_effort,
            self._sandbox,
            self._approval_policy,
        )

        with tempfile.TemporaryDirectory(prefix="codex-translate-") as tmpdir:
            tmp_path = Path(tmpdir)
            schema_path = tmp_path / "result.schema.json"
            last_msg_path = tmp_path / "last_message.txt"
            schema_path.write_text(
                json.dumps(response_schema, ensure_ascii=False),
                encoding="utf-8",
            )

            argv = self._build_argv(
                prompt=prompt,
                model=model,
                schema_path=schema_path,
                last_msg_path=last_msg_path,
            )

            try:
                proc = subprocess.run(
                    argv,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                msg = f"Codex CLI timed out after {self._timeout}s"
                raise RuntimeError(msg) from exc
            except FileNotFoundError as exc:
                msg = (
                    f"codex CLI not found (executable={self._executable!r}) — "
                    f"is it installed and on PATH?"
                )
                raise RuntimeError(msg) from exc

            if proc.returncode != 0:
                stderr = _bounded(proc.stderr)
                msg = f"Codex CLI exited with code {proc.returncode}: {stderr}"
                raise RuntimeError(msg)

            try:
                last_msg = last_msg_path.read_text(encoding="utf-8")
            except OSError as exc:
                msg = (
                    f"Codex CLI did not write {last_msg_path.name} "
                    f"(returncode={proc.returncode}): {exc}"
                )
                raise RuntimeError(msg) from exc

            if not last_msg or not last_msg.strip():
                msg = "Codex CLI produced no final message"
                raise RuntimeError(msg)

            data = _parse_last_message(last_msg)
            result = TranslationResultV1.model_validate(data)

            if result.batch_id != batch.batch_id:
                msg = (
                    f"Codex CLI returned batch_id={result.batch_id!r} but "
                    f"expected {batch.batch_id!r}"
                )
                raise RuntimeError(msg)

            input_tokens, output_tokens, event_count = (
                _parse_event_stream_for_tokens(proc.stdout) if self._json_events else (0, 0, 0)
            )

            meta = TranslationResponseMeta(
                provider="codex-cli",
                model=model,
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
            )

            log.info(
                "Codex CLI translate_batch complete: segments=%d "
                "input_tokens=%d output_tokens=%d events=%d",
                len(result.segments),
                input_tokens,
                output_tokens,
                event_count,
            )
            return TranslationResponse(result=result, meta=meta)


__all__ = ["CodexCLIAdapter"]
