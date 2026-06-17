/**
 * Unit tests for the TS-types codegen helper (S5U-1234, defect 3).
 *
 * The former `PRIMARY_TYPES` hand-map silently skipped any schema not listed in
 * it (5 existing schemas were being dropped). The fix derives the primary type
 * name from each schema's `title` and fails loud on a missing title. These
 * tests pin both invariants: full coverage (no silent skip) and fail-loud.
 */
import { readdir, readFile } from 'node:fs/promises';
import { join, basename, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';

// Import the content-derived helper from the codegen script at repo root.
// @ts-expect-error — .mjs codegen script has no .d.ts; runtime import is fine.
import { derivePrimaryType } from '../../../../scripts/generate_ts_types.mjs';

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..');
const SCHEMA_DIR = join(REPO_ROOT, 'packages', 'schemas', 'jsonschema');

async function schemaStems(): Promise<string[]> {
  const files = (await readdir(SCHEMA_DIR)).filter((f) => f.endsWith('.schema.json'));
  return files.map((f) => basename(f, '.schema.json')).sort();
}

describe('derivePrimaryType — content-derived, fail-loud (S5U-1234)', () => {
  it('resolves a primary type for EVERY committed schema (no silent skip)', async () => {
    const stems = await schemaStems();
    expect(stems.length).toBeGreaterThan(0);

    const resolved: Record<string, string> = {};
    for (const stem of stems) {
      const raw = await readFile(join(SCHEMA_DIR, `${stem}.schema.json`), 'utf-8');
      const schema = JSON.parse(raw);
      // Must not throw and must return a non-empty type name for any real schema.
      const primary = derivePrimaryType(stem, schema);
      expect(primary, `schema '${stem}' must resolve a primary type`).toBeTruthy();
      resolved[stem] = primary;
    }

    // Every schema is covered — count matches, none dropped.
    expect(Object.keys(resolved)).toHaveLength(stems.length);

    // The 5 schemas the old hand-map silently skipped are now covered.
    for (const stem of [
      'page_images_v1',
      'raster_meta_v1',
      'run_summary_v1',
      'translation_qa_record_set_v1',
      'user_feedback_record_set_v1',
    ]) {
      expect(stems, `${stem} fixture must exist`).toContain(stem);
      expect(resolved[stem], `${stem} must resolve a type`).toBeTruthy();
    }
  });

  it('derives the type name from the schema title', () => {
    expect(derivePrimaryType('native_page_v1', { title: 'NativePageV1' })).toBe('NativePageV1');
  });

  it('fails loud (throws naming the stem) when a schema has no title', () => {
    expect(() => derivePrimaryType('mystery_v1', {})).toThrowError(/mystery_v1/);
  });

  it('fails loud on a blank/whitespace title rather than emitting an empty export', () => {
    expect(() => derivePrimaryType('blank_v1', { title: '   ' })).toThrowError(/blank_v1/);
  });
});
