import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

test('review route loads on committed fixture, supports block select + text correction draft + export', async ({ page }) => {
  // Use a committed fixture document that has an en edition in public/documents.
  // Route is lazy; main reader bundle must not be affected (no change to existing specs).
  await page.goto('/documents/icon_dense/en/review/p0001');

  // Basic load
  await expect(page.getByText(/Extraction Review/i)).toBeVisible({ timeout: 10000 });

  // The blocks list should be present
  const blockList = page.locator('.review-blocks-list .review-block-item');
  await expect(blockList.first()).toBeVisible();

  // Select the first block by clicking in the list (hover/click sync exercised)
  await blockList.first().click();

  // Correction panel appears
  await expect(page.locator('.review-correction-panel')).toBeVisible();

  // Draft a text correction (scope defaults to text)
  const textarea = page.locator('.review-correction-panel textarea');
  await textarea.fill('Corrected extraction text for review test');

  // Add the operation
  await page.getByRole('button', { name: /Add operation/i }).click();

  // Now the drawer should list 1 op
  await expect(page.locator('.patch-op-list .op')).toHaveCount(1);

  // Fill required metadata (author + reason) to enable export
  await page.getByPlaceholder('Author (required for export)').fill('s5u-reviewer');
  await page.getByPlaceholder('Reason (required for export)').fill('S5U-1538 e2e: text correction on fixture');

  // Export button enabled
  const exportBtn = page.getByRole('button', { name: /Export patch-/i });
  await expect(exportBtn).toBeEnabled();

  // Trigger export and capture the download
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    exportBtn.click(),
  ]);

  // Filename shape: patch-...json
  const filename = download.suggestedFilename();
  expect(filename).toMatch(/^patch-.*\.json$/);

  // Save and read the payload to assert shape
  const path = await download.path();
  const content = await fs.readFile(path, 'utf8');
  const json = JSON.parse(content);

  // Shape assertions (mirrors what pipeline contract will also validate)
  expect(json.schema_version).toBe('patch_set.v1');
  expect(json.target_kind).toBe('render_page');
  expect(Array.isArray(json.operations)).toBe(true);
  expect(json.operations.length).toBeGreaterThan(0);
  expect(typeof json.reason).toBe('string');
  expect(json.reason.length).toBeGreaterThan(0);
  expect(typeof json.author).toBe('string');

  // One of the ops should be our text replace
  const hasTextOp = json.operations.some(
    (op: any) => op.op === 'replace' && /\/children\//.test(op.path) && op.scope === 'text',
  );
  expect(hasTextOp).toBe(true);
});
