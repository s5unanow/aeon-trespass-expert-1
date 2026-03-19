import { test, expect } from '@playwright/test';

test('walking skeleton reader page renders correctly', async ({ page }) => {
  await page.goto('/documents/walking_skeleton/p0001');

  // Wait for content to load
  await expect(page.getByText('Проверка атаки')).toBeVisible();

  // Check heading is present
  const heading = page.locator('h2.reader-heading');
  await expect(heading).toContainText('Проверка атаки');

  // Check paragraph text
  await expect(page.getByText('Получите 1')).toBeVisible();

  // Check icon is rendered (img with alt text for mapped icons)
  const icon = page.locator('img[data-symbol-id="sym.progress"]');
  await expect(icon).toBeVisible();
  await expect(icon).toHaveAttribute('alt', 'Прогресс');

  // Check source page badge
  await expect(page.getByText('p.1')).toBeVisible();
});
