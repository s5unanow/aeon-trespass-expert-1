# External Integrations

External systems the pipeline talks to and how they are abstracted. All translation/LLM
access goes through a single provider-agnostic contract so providers can be swapped without
touching stage code.

## LLM / translation providers

The pipeline supports multiple translation backends behind one Protocol.

| Concern | Where |
|---|---|
| Provider-agnostic contract | `TranslatorAdapter` (Protocol) — `apps/pipeline/src/atr_pipeline/services/llm/base.py:33` |
| Response shape | `TranslationResponse` / `TranslationResponseMeta` — `services/llm/base.py:13` |
| Adapter selection / construction | `create_translator` — `services/llm/factory.py:232` |
| Concrete adapters | `anthropic_adapter.py`, `gemini_adapter.py`, `codex_cli_adapter.py`, `agy_cli_adapter.py` (`services/llm/`) |
| Fallback chaining | `services/llm/fallback.py` |
| Provider switch spec | `docs/specs/translation-providers.md` |

Add a provider by implementing `TranslatorAdapter` and wiring it into `create_translator` —
never call a vendor SDK directly from a stage.

| Avoid | Prefer |
|---|---|
| Importing `anthropic` / `google-genai` inside a stage | Depend on `TranslatorAdapter`; select via `create_translator` |
| Hardcoding a provider name in stage logic | Configure the provider; document the switch in `docs/specs/translation-providers.md` |

LLM SDKs are optional extras, not core deps — `[project.optional-dependencies].llm`
(`apps/pipeline/pyproject.toml`): `openai`, `anthropic`, `google-genai`.

## PDF & layout extraction

| Integration | Purpose | Source |
|---|---|---|
| PyMuPDF | Native PDF text/geometry extraction | core dep `pyproject.toml`; `docs/adrs/ADR-004-pymupdf-as-native-pdf-extractor.md` |
| Docling | Layout evidence (`layout` extra) | `docs/adrs/ADR-005-docling-as-layout-evidence.md` |
| OpenCV / Pillow | Symbol template matching | core deps; `docs/adrs/ADR-006-symbol-catalog-and-template-matching.md` |

Tesseract was retired from OCR fallback — `docs/adrs/ADR-013-retire-tesseract-from-ocr-fallback.md`.

## Codex CLI smoke (opt-in)

Tests that shell out to a real `codex` CLI are gated behind `@pytest.mark.codex_live` and
`ATR_CODEX_LIVE_SMOKE=1` (`apps/pipeline/pyproject.toml:45`) so normal runs never hit an
external binary. Known limitation: `codex exec` hangs headlessly (see repo memory /
`docs/specs/translation-providers.md`).

## Work-item tracker (Linear)

Issue lookup/create is via the Linear MCP integration — see `.ai-run/guides/project.md`
(`## Ticket Adapter`) and `.ai-run/guides/integration/ticket-flow.md`.

## Do / Don't

| ✅ DO | ❌ DON'T |
|---|---|
| Route all translation through `TranslatorAdapter` | Call a vendor SDK from stage code |
| Keep LLM SDKs as optional extras | Promote a provider SDK to a core dependency |
| Gate live-CLI tests behind the opt-in env var | Shell to `codex`/`agy` in the default test run |
