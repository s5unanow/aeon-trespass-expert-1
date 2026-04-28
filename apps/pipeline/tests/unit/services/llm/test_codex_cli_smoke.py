"""Opt-in real-subprocess smoke test for the Codex CLI translation provider.

This test is **deliberately excluded from default `pytest`**. It is the
only place in the test suite that may shell out to a real ``codex``
binary, and even then only when both:

1. the test is selected via ``-m codex_live`` (a registered pytest marker);
2. the operator sets the env var ``ATR_CODEX_LIVE_SMOKE=1`` to acknowledge
   that a paid Codex call is about to happen.

Both gates are required. ``-m codex_live`` alone collects the test but the
body's first statement skips when ``ATR_CODEX_LIVE_SMOKE`` is unset; the
env var alone has no effect because the marker filter on the operator's
invocation is what discovers the test.

Documented invocation:

    ATR_CODEX_LIVE_SMOKE=1 uv run pytest -m codex_live \
        apps/pipeline/tests/unit/services/llm/test_codex_cli_smoke.py -v

The test loads exactly **one** committed fixture batch
(``packages/fixtures/sample_documents/walking_skeleton/expected/translation_batch.p0001.json``),
runs the configured Codex CLI adapter, asserts the response is
well-formed, and writes the captured response under ``tmp/`` (gitignored)
for operator inspection. It does NOT write to ``packages/fixtures/`` or
to ``artifacts/`` — see S5U-748 §5 must-refuse table.

Red-before posture (S5U-615):
    Red-before confirmation: N/A — the smoke test exercises an opt-in
    path that is skipped by default; no production code-path is gated
    on it. The body of the test verifies an existing invariant
    (CodexCLIAdapter end-to-end happy path) against a real subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from atr_pipeline.config.models import (
    CLIProviderOptions,
    TranslationConfig,
    TranslationProviderOptions,
)
from atr_pipeline.services.llm.factory import create_translator
from atr_schemas.translation_batch_v1 import TranslationBatchV1

# Walking-skeleton fixture — the single small page we translate end-to-end.
_FIXTURE_BATCH_PATH = (
    Path(__file__).resolve().parents[5]  # repo root
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "expected"
    / "translation_batch.p0001.json"
)

# Output directory. ``tmp/`` is gitignored at the repo root.
_SMOKE_OUTPUT_DIR = Path(__file__).resolve().parents[5] / "tmp"

# Preflight subprocess timeout — distinct from the translate call's timeout.
_PREFLIGHT_TIMEOUT_SECONDS = 5


@pytest.mark.codex_live
def test_codex_cli_smoke_translates_walking_skeleton_page() -> None:
    """Smoke: run real Codex on one fixture page, assert response well-formed.

    Skipped unless the operator opts in via ``ATR_CODEX_LIVE_SMOKE=1``.
    """
    if os.environ.get("ATR_CODEX_LIVE_SMOKE") != "1":
        pytest.skip(
            "Codex CLI smoke test is opt-in. To run it: set "
            "ATR_CODEX_LIVE_SMOKE=1 AND select with -m codex_live. "
            "See docs/specs/translation-providers.md.",
        )

    # Preflight — distinguish "codex not installed / not authed" from a
    # subprocess parse failure that would only surface after a 600s
    # translate-call timeout.
    try:
        proc = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            timeout=_PREFLIGHT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("codex CLI is not on PATH; cannot run live smoke")
    except subprocess.TimeoutExpired:
        pytest.skip("codex --version timed out — environment is broken")
    if proc.returncode != 0:
        pytest.skip(
            f"codex --version returned non-zero ({proc.returncode}); "
            f"likely auth or install issue: {proc.stderr[:200]}",
        )

    # Load the exactly-one fixture batch.
    if not _FIXTURE_BATCH_PATH.exists():
        pytest.skip(f"walking-skeleton batch fixture not present: {_FIXTURE_BATCH_PATH}")
    batch_data = json.loads(_FIXTURE_BATCH_PATH.read_text(encoding="utf-8"))
    batch = TranslationBatchV1.model_validate(batch_data)

    # Configure the recommended Codex CLI deployment shape — the same
    # values pinned by the S5U-747 factory tests.
    config = TranslationConfig(
        provider="codex-cli",
        model_default="gpt-5.5",
        fallback_provider="",
        provider_options=TranslationProviderOptions(
            cli=CLIProviderOptions(
                reasoning_effort="xhigh",
                sandbox="read-only",
                approval_policy="never",
                timeout_seconds=900,
            ),
        ),
    )
    adapter = create_translator(config)

    response = adapter.translate_batch(batch)

    # Well-formedness assertions — the schema is enforced upstream by
    # ``--output-schema`` and TranslationResultV1 validation; here we
    # cross-check against the request.
    assert response.result.batch_id == batch.batch_id
    assert len(response.result.segments) == len(batch.segments), (
        f"segment-count mismatch: response={len(response.result.segments)} "
        f"request={len(batch.segments)}"
    )
    for translated in response.result.segments:
        assert translated.target_inline, f"segment {translated.segment_id} has empty target_inline"

    # Persist the response under tmp/ for operator inspection. tmp/ is
    # gitignored; no fixture or artifact pollution.
    _SMOKE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    output_path = _SMOKE_OUTPUT_DIR / f"smoke-s5u-748-{timestamp}.json"
    output_path.write_text(
        response.result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    # Sanity: the output stayed inside tmp/. Defensive against any future
    # path-construction mistake.
    assert output_path.is_relative_to(_SMOKE_OUTPUT_DIR), (
        f"smoke output escaped tmp/: {output_path}"
    )
