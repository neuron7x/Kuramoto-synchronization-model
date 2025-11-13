/**
 * Accessibility tests for Monitoring View
 * Tests ARIA labels, keyboard navigation, and screen reader compatibility
 */

import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { renderMonitoringView } from '../../src/views/monitoring.js';

const SAMPLE_MONITORING = {
  controls: {
    killSwitch: { enabled: false, lastTriggered: null },
    circuitBreaker: { state: 'closed', trips: 0 },
  },
  metrics: {
    latency: [
      { timestamp: Date.now() - 300_000, value: 12 },
      { timestamp: Date.now() - 240_000, value: 15 },
      { timestamp: Date.now() - 180_000, value: 11 },
      { timestamp: Date.now() - 120_000, value: 14 },
      { timestamp: Date.now() - 60_000, value: 13 },
    ],
    throughput: 1250,
    errorRate: 0.02,
  },
};

const BASE_TEMPLATE = `
  <!DOCTYPE html>
  <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>TradePulse Monitoring</title>
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
      <main id="app" aria-label="Monitoring dashboard"></main>
    </body>
  </html>
`;

async function mountMonitoringFixture(page: Page) {
  const view = renderMonitoringView(SAMPLE_MONITORING);
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

test.describe('Monitoring View Accessibility', () => {
  test('has proper ARIA labels on charts', async ({ page }) => {
    await mountMonitoringFixture(page);
    const charts = await page.locator('[role="img"]').all();
    
    for (const chart of charts) {
      const ariaLabel = await chart.getAttribute('aria-label');
      expect(ariaLabel).toBeTruthy();
    }
  });

  test('passes axe-core accessibility scan', async ({ page }) => {
    await mountMonitoringFixture(page);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    
    expect(results.violations).toEqual([]);
    
    test.info().attach('axe-report', {
      body: JSON.stringify(results, null, 2),
      contentType: 'application/json',
    });
  });

  test('supports keyboard navigation', async ({ page }) => {
    await mountMonitoringFixture(page);
    
    // Tab through interactive elements
    await page.keyboard.press('Tab');
    const firstFocusable = await page.evaluate(() => document.activeElement?.tagName);
    expect(['A', 'BUTTON', 'INPUT', 'SELECT']).toContain(firstFocusable);
  });

  test('has sufficient color contrast', async ({ page }) => {
    await mountMonitoringFixture(page);
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2aa'])
      .include('.tp-view')
      .analyze();
    
    const contrastViolations = results.violations.filter(
      (v) => v.id === 'color-contrast'
    );
    expect(contrastViolations).toEqual([]);
  });

  test('provides screen reader friendly text', async ({ page }) => {
    await mountMonitoringFixture(page);
    const srOnlyElements = await page.locator('.tp-sr-only').all();
    
    for (const element of srOnlyElements) {
      const text = await element.textContent();
      expect(text?.trim().length).toBeGreaterThan(0);
    }
  });
});
