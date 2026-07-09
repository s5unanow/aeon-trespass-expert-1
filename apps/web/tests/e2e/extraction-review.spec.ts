import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('reviewer drafts and downloads a text correction patch', async ({ page }) => {
  await page.goto('/documents/review_fixture/en/review/p0001');

  await expect(page.getByRole('heading', { name: 'Extraction review' })).toBeVisible();
  await expect(page.locator('.review-header').getByText('Review Fixture')).toBeVisible();

  const overlayMarker = page.getByRole('button', { name: /Select block p0001\.b002/ });
  await overlayMarker.hover();
  await expect(page.locator('[data-review-block-id="p0001.b002"]')).toHaveClass(/is-hovered/);
  await overlayMarker.click();

  await expect(page.locator('[data-review-block-id="p0001.b002"]')).toHaveClass(/is-selected/);
  await expect(page.getByRole('heading', { name: 'Correct p0001.b002' })).toBeVisible();

  await page.getByLabel('Author').fill('Reviewer One');
  await page.getByLabel('Patch reason').fill('Correct extraction typo');
  await page.getByLabel('Corrected text').fill('Corrected body text.');
  await page.getByRole('button', { name: 'Draft text correction' }).click();

  await expect(page.getByText('/blocks/1/children/0')).toBeVisible();

  await page.reload();
  await expect(page.getByText('/blocks/1/children/0')).toBeVisible();
  await expect(page.getByLabel('Author')).toHaveValue('Reviewer One');
  await expect(page.getByLabel('Patch reason')).toHaveValue('Correct extraction typo');

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download patch JSON' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(
    /^patch-review_fixture-en-p0001-\d{4}-\d{2}-\d{2}T.*Z\.json$/,
  );

  const path = await file.path();
  expect(path).toBeTruthy();
  const json = JSON.parse(await readFile(path!, 'utf8'));

  expect(json.schema_version).toBe('patch_set.v1');
  expect(json.target_kind).toBe('render_page');
  expect(json.author).toBe('Reviewer One');
  expect(json.reason).toBe('Correct extraction typo');
  expect(json.operations).toEqual([
    {
      op: 'replace',
      path: '/blocks/1/children/0',
      value: { kind: 'text', text: 'Corrected body text.', marks: [] },
      scope: 'text',
    },
  ]);
});
