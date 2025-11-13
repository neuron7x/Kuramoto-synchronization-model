import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { renderOverviewView } from '../../src/views/overview.js';

const SAMPLE_OVERVIEW = {
  stats: {
    totalOrders: 150,
    activePositions: 12,
    dailyPnL: 2450.50,
    winRate: 0.68,
  },
  recentTrades: [
    {
      id: 'trade-1',
      symbol: 'AAPL',
      side: 'BUY',
      quantity: 100,
      price: 175.50,
      timestamp: Date.now() - 300_000,
    },
  ],
};

const BASE_TEMPLATE = `
  <!DOCTYPE html>
  <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>TradePulse Overview</title>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        body {
          font-family: system-ui, sans-serif;
          margin: 0;
          padding: 2rem;
          background: #0f172a;
          color: #e2e8f0;
        }
        main {
          max-width: 1200px;
          margin: 0 auto;
        }
      </style>
    </head>
    <body>
      <main id="app" aria-label="Overview dashboard"></main>
    </body>
  </html>
`;

async function mountOverviewFixture(page: Page) {
  const view = renderOverviewView(SAMPLE_OVERVIEW);
  await page.setContent(BASE_TEMPLATE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(
    ({ html }: { html: string }) => {
      const root = document.getElementById('app');
      if (!root) throw new Error('Fixture root missing');
      root.innerHTML = html;
    },
    { html: view.html },
  );
  return { view };
}

test.describe('Overview View Tests', () => {
  test('renders overview with key metrics', async ({ page }) => {
    await mountOverviewFixture(page);
    const heading = await page.locator('h1, h2').first();
    await expect(heading).toBeVisible();
  });

  test('passes accessibility checks', async ({ page }) => {
    await mountOverviewFixture(page);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });

  test('displays stats correctly', async ({ page }) => {
    await mountOverviewFixture(page);
    await expect(page.locator('text=150')).toBeVisible(); // totalOrders
    await expect(page.locator('text=12')).toBeVisible(); // activePositions
  });
});
