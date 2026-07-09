import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

test('drafts, persists, and downloads a typed text correction', async ({ page }) => {
  await page.goto('/documents/extraction_review/en/review/p0001');
  await page.evaluate(() => localStorage.clear());
  await page.reload();

  await expect(page.getByRole('heading', { name: 'Extraction review' })).toBeVisible();
  const overlay = page.getByRole('button', { name: 'Select p0001.b002 on facsimile' });
  const renderedBlock = page.locator('[data-block-ref="p0001.b002"]');
  await overlay.hover();
  await expect(renderedBlock).toHaveClass(/is-active/);
  await overlay.click();
  await expect(overlay).toHaveAttribute('aria-pressed', 'true');
  await expect(renderedBlock).toHaveClass(/is-selected/);
  await expect(page.getByRole('heading', { name: 'Correct p0001.b002' })).toBeVisible();

  await page.getByLabel('Corrected text').fill('Move up to two spaces.');
  await page.getByRole('button', { name: 'Add text correction' }).click();
  await expect(page.getByText('1 operation')).toBeVisible();
  await expect(page.getByText('/blocks/1/children/0/text')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Export patch JSON' })).toBeDisabled();

  await page.reload();
  await expect(page.getByText('1 operation')).toBeVisible();

  await page.getByLabel('Author').fill('e2e-reviewer');
  await page.getByLabel('Reason').fill('Correct OCR typo');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export patch JSON' }).click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(/^patch-extraction_review-en-p0001-.*\.json$/);
  const downloadPath = await download.path();
  expect(downloadPath).toBeTruthy();
  const exported = JSON.parse(await readFile(downloadPath!, 'utf-8'));
  expect(exported.target_kind).toBe('render_page');
  expect(exported.reason).toBe('Correct OCR typo');
  expect(exported.author).toBe('e2e-reviewer');
  expect(exported.provenance.source_confidence).toBe(0.82);
  expect(exported.operations).toEqual([
    {
      op: 'replace',
      path: '/blocks/1/children/0/text',
      value: 'Move up to two spaces.',
      scope: 'text',
    },
  ]);
});
