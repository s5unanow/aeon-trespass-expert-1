/**
 * E2E for the extraction-review route (S5U-1539): a reviewer selects a block,
 * drafts a text correction, and downloads a schema-valid `patch_set.v1`.
 *
 * Runs against the committed `review_sample` fixture document. Does not touch
 * any existing reader route or visual snapshot.
 */
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

const REVIEW_URL = '/documents/review_sample/en/review/p0001';

test('draft a text correction and export a patch set', async ({ page }) => {
  await page.goto(REVIEW_URL);

  // The lazy route resolves and renders the block list + facsimile overlay.
  await expect(page.getByRole('heading', { name: /Extraction review/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Block 1:/ })).toBeVisible();

  // Select block 2 (a paragraph) and confirm facsimile↔list sync.
  await page.getByRole('button', { name: /Select block 2/ }).click();
  await expect(page.getByRole('button', { name: /^Block 2:/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  // Draft a text correction.
  await page.getByLabel('Corrected text').fill("Roll dice equal to the titan's ATTACK value.");
  await page.getByLabel('Reason (required)').fill('fix casing of ATTACK');
  await page.getByRole('button', { name: 'Add correction' }).click();

  // Export is blocked until an author is provided.
  const exportButton = page.getByRole('button', { name: 'Download patch set' });
  await expect(exportButton).toBeDisabled();
  await page.getByLabel('Author (required)').fill('reviewer@example.com');
  await expect(exportButton).toBeEnabled();

  // Download and inspect the exported patch set.
  const downloadPromise = page.waitForEvent('download');
  await exportButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(
    /^patch-review_sample-en-p0001-.*\.json$/,
  );

  const filePath = await download.path();
  const patchSet = JSON.parse(readFileSync(filePath, 'utf-8'));
  expect(patchSet.schema_version).toBe('patch_set.v1');
  expect(patchSet.target_kind).toBe('render_page');
  expect(patchSet.author).toBe('reviewer@example.com');
  expect(patchSet.operations).toHaveLength(1);
  expect(patchSet.operations[0].path).toBe('/blocks/1/children/0/text');
  expect(patchSet.operations[0].scope).toBe('text');
  expect(patchSet.operations[0].value).toBe("Roll dice equal to the titan's ATTACK value.");
});
