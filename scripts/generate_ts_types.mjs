#!/usr/bin/env node
/**
 * Generate TypeScript types from JSON Schema files.
 *
 * Input:  packages/schemas/jsonschema/*.schema.json
 * Output: packages/schemas/ts/src/generated/*.ts
 *
 * These are generated files — do not edit by hand.
 */

import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { join, basename, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const SCHEMA_DIR = join(ROOT, 'packages', 'schemas', 'jsonschema');
const OUTPUT_DIR = join(ROOT, 'packages', 'schemas', 'ts', 'src', 'generated');

// Map from schema file stem to the primary exported type name
const PRIMARY_TYPES = {
  assistant_citation_v1: 'AssistantCitationV1',
  assistant_pack_v1: 'AssistantPackV1',
  asset_class_v1: 'AssetClassV1',
  asset_occurrence_v1: 'AssetOccurrenceV1',
  asset_registry_v1: 'AssetRegistryV1',
  asset_v1: 'AssetV1',
  build_manifest_v1: 'BuildManifestV1',
  concept_registry_v1: 'ConceptRegistryV1',
  glossary_payload_v1: 'GlossaryPayloadV1',
  layout_page_v1: 'LayoutPageV1',
  native_page_v1: 'NativePageV1',
  nav_payload_v1: 'NavPayloadV1',
  page_evidence_v1: 'PageEvidenceV1',
  page_ir_v1: 'PageIRV1',
  patch_set_v1: 'PatchSetV1',
  qa_record_v1: 'QARecordV1',
  qa_summary_v1: 'QASummaryV1',
  render_page_v1: 'RenderPageV1',
  resolved_page_v1: 'ResolvedPageV1',
  review_pack_v1: 'ReviewPackV1',
  rule_chunk_v1: 'RuleChunkV1',
  run_manifest_v1: 'RunManifestV1',
  search_docs_v1: 'SearchDocsV1',
  source_manifest_v1: 'SourceManifestV1',
  symbol_catalog_v1: 'SymbolCatalogV1',
  symbol_match_set_v1: 'SymbolMatchSetV1',
  translation_batch_v1: 'TranslationBatchV1',
  translation_result_v1: 'TranslationResultV1',
  waiver_set_v1: 'WaiverSetV1',
};

async function main() {
  await mkdir(OUTPUT_DIR, { recursive: true });

  const files = (await readdir(SCHEMA_DIR)).filter((f) => f.endsWith('.schema.json'));

  const exportLines = [];

  for (const file of files.sort()) {
    const schemaPath = join(SCHEMA_DIR, file);
    const raw = await readFile(schemaPath, 'utf-8');
    const schema = JSON.parse(raw);

    const tsName = basename(file, '.schema.json');
    const ts = await compile(schema, schema.title || tsName, {
      bannerComment: '/* Auto-generated from JSON Schema — do not edit */\n',
      additionalProperties: false,
      style: { semi: true, singleQuote: true },
    });

    const outPath = join(OUTPUT_DIR, `${tsName}.ts`);
    await writeFile(outPath, ts, 'utf-8');
    console.log(`  wrote packages/schemas/ts/src/generated/${tsName}.ts`);

    // Use namespace-style re-export to avoid name collisions
    const camelName = tsName.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
    exportLines.push(`export * as ${camelName} from './generated/${tsName}';`);
  }

  // Also export the primary types directly for convenience
  const directExports = [];
  for (const file of files.sort()) {
    const tsName = basename(file, '.schema.json');
    const primary = PRIMARY_TYPES[tsName];
    if (primary) {
      directExports.push(`export type { ${primary} } from './generated/${tsName}';`);
    }
  }

  const indexPath = join(OUTPUT_DIR, '..', 'index.ts');
  const indexContent =
    '// Auto-generated barrel — do not edit\n\n' +
    '// Namespace re-exports (all types per schema)\n' +
    exportLines.join('\n') +
    '\n\n' +
    '// Direct top-level type exports\n' +
    directExports.join('\n') +
    '\n';
  await writeFile(indexPath, indexContent, 'utf-8');
  console.log(`  wrote packages/schemas/ts/src/index.ts`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
