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

/**
 * Derive the primary exported type name for a schema, content-derived from its
 * `title` field (the same value `json-schema-to-typescript` uses as the root
 * type name). This replaces the former hand-maintained `PRIMARY_TYPES` map,
 * which silently skipped any schema not listed in it (5 existing schemas were
 * being dropped — S5U-1234). Fail loud, not silent: a schema with no usable
 * `title` throws rather than being quietly omitted from the direct exports.
 *
 * @param {string} stem schema file stem, e.g. `native_page_v1`
 * @param {{ title?: unknown }} schema parsed JSON Schema object
 * @returns {string} the primary type name (the schema `title`)
 */
export function derivePrimaryType(stem, schema) {
  const title = schema?.title;
  if (typeof title !== 'string' || title.trim() === '') {
    throw new Error(
      `Schema '${stem}.schema.json' has no usable 'title' — cannot derive a ` +
        `primary TypeScript type name. Add a title to the Pydantic model (or ` +
        `its schema) so codegen can export it; do not silently skip it.`,
    );
  }
  return title;
}

async function main() {
  await mkdir(OUTPUT_DIR, { recursive: true });

  const files = (await readdir(SCHEMA_DIR)).filter((f) => f.endsWith('.schema.json'));

  const exportLines = [];
  // Direct top-level type exports — one per schema, content-derived from the
  // schema `title`. derivePrimaryType throws (→ non-zero exit) on any schema
  // without a usable title, so no schema is ever silently skipped (S5U-1234).
  const directExports = [];

  for (const file of files.sort()) {
    const schemaPath = join(SCHEMA_DIR, file);
    const raw = await readFile(schemaPath, 'utf-8');
    const schema = JSON.parse(raw);

    const tsName = basename(file, '.schema.json');
    const primary = derivePrimaryType(tsName, schema);
    const ts = await compile(schema, primary, {
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
    directExports.push(`export type { ${primary} } from './generated/${tsName}';`);
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

// Run only when invoked directly (`node scripts/generate_ts_types.mjs`), not
// when imported by a test for `derivePrimaryType`.
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
