/**
 * Browser-level extraction regression checks for curated EN pages.
 *
 * Complements S5U-286 payload-level verification by asserting that
 * the web reader renders curated EN/source-edition pages correctly.
 *
 * Each test loads a curated page via the preview server, checks DOM
 * structure, and captures console errors as failures.
 */
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';

// ---------------------------------------------------------------------------
// Console error collector — shared across all tests
// ---------------------------------------------------------------------------

function collectConsoleErrors(page: Page): ConsoleMessage[] {
  const errors: ConsoleMessage[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      // Ignore 404s from manifest fetches — layout sidebar is best-effort
      const text = msg.text();
      if (text.includes('manifest.json') || text.includes('Failed to load resource')) return;
      errors.push(msg);
    }
  });
  return errors;
}

// ---------------------------------------------------------------------------
// Curated page specs — mirrors configs/golden_sets/*.toml
// ---------------------------------------------------------------------------

interface PageSpec {
  documentId: string;
  pageId: string;
  title: string;
  blockCount: number;
  /** Expected block kind counts (verified per-kind, not ordered). */
  blockKinds: string[];
  /** Number of visible icon elements (data-symbol-id) expected. */
  symbolCount: number;
  /** Source page number shown in badge. */
  sourcePageNumber: number;
}

const CURATED_PAGES: PageSpec[] = [
  {
    documentId: 'icon_dense',
    pageId: 'p0001',
    title: 'Action Costs',
    blockCount: 4,
    blockKinds: ['heading', 'paragraph', 'paragraph', 'paragraph'],
    symbolCount: 6,
    sourcePageNumber: 1,
  },
  {
    documentId: 'multi_column',
    pageId: 'p0001',
    title: 'Combat Rules',
    blockCount: 5,
    blockKinds: ['heading', 'paragraph', 'paragraph', 'paragraph', 'paragraph'],
    symbolCount: 0,
    sourcePageNumber: 1,
  },
  {
    documentId: 'table_callout',
    pageId: 'p0001',
    title: 'Equipment Table',
    blockCount: 4,
    blockKinds: ['heading', 'table', 'callout', 'paragraph'],
    symbolCount: 0,
    sourcePageNumber: 1,
  },
  {
    documentId: 'figure_caption',
    pageId: 'p0001',
    title: 'Titan Anatomy',
    blockCount: 3,
    blockKinds: ['heading', 'paragraph', 'figure'],
    symbolCount: 0,
    sourcePageNumber: 1,
  },
];

// CSS selectors for each block kind as rendered by BlockRenderer
const BLOCK_KIND_SELECTOR: Record<string, string> = {
  heading: '.reader-heading',
  paragraph: '.reader-paragraph',
  table: '.reader-table',
  callout: '.reader-callout',
  figure: '.reader-figure',
  divider: '.reader-divider',
};

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

for (const spec of CURATED_PAGES) {
  test.describe(`EN extraction: ${spec.documentId}/${spec.pageId}`, () => {
    let consoleErrors: ConsoleMessage[];

    test.beforeEach(async ({ page }) => {
      consoleErrors = collectConsoleErrors(page);
    });

    test('page loads without errors', async ({ page }) => {
      await page.goto(`/documents/${spec.documentId}/en/${spec.pageId}`);
      const content = page.locator('.reader-content');
      await expect(content.getByText(spec.title)).toBeVisible();
      expect(consoleErrors).toHaveLength(0);
    });

    test('heading renders with correct text', async ({ page }) => {
      await page.goto(`/documents/${spec.documentId}/en/${spec.pageId}`);
      const heading = page.locator('h2.reader-heading');
      await expect(heading).toContainText(spec.title);
    });

    test('block count and kinds match spec', async ({ page }) => {
      await page.goto(`/documents/${spec.documentId}/en/${spec.pageId}`);
      const content = page.locator('.reader-content');
      await expect(content.getByText(spec.title)).toBeVisible();
      // Count all rendered blocks by their CSS class selectors
      const allSelectors = Object.values(BLOCK_KIND_SELECTOR).join(', ');
      const blocks = content.locator(allSelectors);
      await expect(blocks).toHaveCount(spec.blockCount);

      // Verify each block kind appears the expected number of times
      const kindCounts = new Map<string, number>();
      for (const kind of spec.blockKinds) {
        kindCounts.set(kind, (kindCounts.get(kind) ?? 0) + 1);
      }
      for (const [kind, expectedCount] of kindCounts) {
        const selector = BLOCK_KIND_SELECTOR[kind];
        if (selector) {
          await expect(content.locator(selector)).toHaveCount(expectedCount);
        }
      }
    });

    test('symbol icons render correctly', async ({ page }) => {
      await page.goto(`/documents/${spec.documentId}/en/${spec.pageId}`);
      await expect(page.locator('.reader-content').getByText(spec.title)).toBeVisible();

      const icons = page.locator('[data-symbol-id]');
      await expect(icons).toHaveCount(spec.symbolCount);

      // Every visible icon must have alt text or aria-label
      for (let i = 0; i < spec.symbolCount; i++) {
        const icon = icons.nth(i);
        const alt = await icon.getAttribute('alt');
        const ariaLabel = await icon.getAttribute('aria-label');
        expect(alt || ariaLabel).toBeTruthy();
      }
    });

    test('source page badge shows correct number', async ({ page }) => {
      await page.goto(`/documents/${spec.documentId}/en/${spec.pageId}`);
      await expect(page.getByText(`p.${spec.sourcePageNumber}`)).toBeVisible();
    });

    test('no console errors during render', async ({ page }) => {
      await page.goto(`/documents/${spec.documentId}/en/${spec.pageId}`);
      await expect(page.locator('.reader-content').getByText(spec.title)).toBeVisible();
      await page.waitForLoadState('networkidle');
      expect(consoleErrors.map((e) => e.text())).toEqual([]);
    });
  });
}

// ---------------------------------------------------------------------------
// Block-specific assertions for complex block types
// ---------------------------------------------------------------------------

test.describe('EN extraction: table_callout block-specific checks', () => {
  test('table block has role="table"', async ({ page }) => {
    await page.goto('/documents/table_callout/en/p0001');
    await expect(page.locator('.reader-content').getByText('Equipment Table')).toBeVisible();

    const table = page.locator('.reader-table');
    await expect(table).toHaveAttribute('role', 'table');
    await expect(table).toContainText('Iron Sword');
  });

  test('callout block has warning variant', async ({ page }) => {
    await page.goto('/documents/table_callout/en/p0001');
    await expect(page.locator('.reader-content').getByText('Equipment Table')).toBeVisible();

    const callout = page.locator('.reader-callout');
    await expect(callout).toHaveAttribute('data-variant', 'warning');
    await expect(callout).toContainText('Cursed items');
  });
});

test.describe('EN extraction: figure_caption block-specific checks', () => {
  test('figure block renders with image element', async ({ page }) => {
    await page.goto('/documents/figure_caption/en/p0001');
    await expect(page.locator('.reader-content').getByText('Titan Anatomy')).toBeVisible();

    const figure = page.locator('.reader-figure');
    await expect(figure).toBeVisible();
    const img = figure.locator('.reader-figure-img');
    await expect(img).toHaveCount(1);
    await expect(img).toHaveAttribute('alt', 'asset.fig.p0001.01');
  });

  test('figure has caption text', async ({ page }) => {
    await page.goto('/documents/figure_caption/en/p0001');
    await expect(page.locator('.reader-content').getByText('Titan Anatomy')).toBeVisible();

    const caption = page.locator('.reader-figure-caption');
    await expect(caption).toContainText('Titan weak points');
  });
});

test.describe('EN extraction: icon_dense block-specific checks', () => {
  test('all icons use mapped sym.progress image', async ({ page }) => {
    await page.goto('/documents/icon_dense/en/p0001');
    await expect(page.locator('.reader-content').getByText('Action Costs')).toBeVisible();

    const icons = page.locator('img[data-symbol-id="sym.progress"]');
    await expect(icons).toHaveCount(6);

    // Each icon should reference the progress icon asset
    for (let i = 0; i < 6; i++) {
      await expect(icons.nth(i)).toHaveAttribute('src', '/icons/stat_progress.png');
      await expect(icons.nth(i)).toHaveAttribute('alt', 'Progress');
    }
  });
});

// ---------------------------------------------------------------------------
// Visual snapshot for regression detection (icon_dense — most complex layout)
// ---------------------------------------------------------------------------

test('visual snapshot: icon_dense EN page', async ({ page }) => {
  await page.goto('/documents/icon_dense/en/p0001');
  await expect(page.locator('.reader-content').getByText('Action Costs')).toBeVisible();

  const content = page.locator('.reader-content');
  await expect(content).toHaveScreenshot('icon-dense-en-p0001.png');
});
