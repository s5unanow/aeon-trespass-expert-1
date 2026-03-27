# Extraction Review Workflow

Run extraction without translation for specific pages and review the English
source edition in the web reader.

## Quick start

```bash
# 1. Run extraction-only pipeline for specific pages
atr run --doc ato_core_v1_1 --edition en --pages 15,18-20

# 2. Export EN renders to the web public directory
make export-en

# 3. Start the dev server and open the reader
cd apps/web && pnpm dev
# Open http://localhost:3001/documents/ato_core_v1_1/en/p0015
```

## Step-by-step

### 1. Run extraction for target pages

```bash
atr run --doc <DOC_ID> --edition en --pages <PAGE_SPEC>
```

- `--edition en` skips the translation stage and renders from English IR
- `--pages` accepts single pages (`15`), ranges (`15-20`), and comma-separated
  lists (`15,18-20`)
- Stages executed: ingest, extract_native, extract_layout, symbols, structure,
  render, qa, publish

### 2. Export to the web reader

```bash
# EN only (fast)
make export-en

# Both EN and RU
make export

# Custom document
uv run python scripts/export_to_web.py --doc walking_skeleton --edition en
```

The export script writes to edition-scoped paths that the web reader expects:

```
apps/web/public/documents/{doc_id}/{edition}/
  manifest.json
  data/render_page.{page_id}.json
```

### 3. Review in the browser

Start the dev server:

```bash
cd apps/web && pnpm dev
```

Navigate to `http://localhost:3001/documents/{doc_id}/en/{page_id}`.

The reader has an **EN/RU edition switcher** in the navigation bar. When both
editions are exported, you can toggle between them to compare extraction output
against translation output.

### 4. Iterate

After reviewing, fix extraction issues and re-run:

```bash
atr run --doc ato_core_v1_1 --edition en --pages 15
make export-en
# Reload the browser
```

## Diagnostic commands

These commands provide extraction quality signals without needing the web reader:

```bash
# Invariant checks — validates extraction output structure
atr verify-extraction --doc <DOC_ID> --pages <PAGE_SPEC>

# Cross-stage reference integrity
atr verify-refs --doc <DOC_ID> --pages <PAGE_SPEC>

# Non-blocking audit with confidence scores
atr audit --doc <DOC_ID> --pages <PAGE_SPEC>

# Evaluation against golden fixtures
atr eval --golden-set <NAME> --doc <DOC_ID> --pages <PAGE_SPEC>
```

## Architecture notes

- The pipeline stores artifacts in `artifacts/{doc_id}/` with the edition
  tracked in the run registry
- The render stage loads RU IR (preferred) or EN IR depending on what is
  available; `--edition en` ensures only EN IR is produced
- The export script scores render versions per page: EN export prefers
  Latin text, RU export prefers Cyrillic text
- The web reader tries edition-scoped paths first
  (`/documents/{doc}/en/data/...`), falling back to root paths for
  backward compatibility
