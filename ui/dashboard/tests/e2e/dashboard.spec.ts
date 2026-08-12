import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { renderSignalsView } from '../../src/views/signals.js';

declare global {
  interface Window {
    __renderMetrics?: {
      renderDuration: number;
      summary: {
        activeCount: number;
        counts: Record<string, number>;
        averageStrength: number;
        maxStrength: number;
      };
      totalSignals: number;
    };
  }
}

const SEMANTIC_GUARDRAIL_ENABLED = process.env.UI_SEMANTIC_BASELINE === 'true';

const SAMPLE_SIGNALS = [
  {
    id: 'sig-1',
    symbol: 'AAPL',
    direction: 'BUY',
    strength: 0.86,
    timestamp: Date.now() - 45_000,
    ttl_seconds: 300,
    confidence: 0.94,
    metadata: {
      strategy: 'momentum',
      horizon: '1h',
    },
  },
  {
    id: 'sig-2',
    symbol: 'MSFT',
    direction: 'SELL',
    strength: 0.42,
    timestamp: Date.now() - 120_000,
    ttl_seconds: 180,
    confidence: 0.61,
    metadata: {
      strategy: 'mean_reversion',
      horizon: '30m',
    },
  },
  {
    id: 'sig-3',
    symbol: 'NVDA',
    direction: 'BUY',
    strength: 0.73,
    timestamp: Date.now() - 12_000,
    ttl_seconds: 90,
    confidence: 0.88,
    metadata: {
      strategy: 'volatility_breakout',
      horizon: '15m',
    },
  },
];

const BASE_TEMPLATE = `
  <!DOCTYPE html>
  <html lang="en">
    <head>
      <meta charset="utf-8" />
      <title>GeoSync Signals Fixture</title>
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
        a {
          color: #38bdf8;
        }
      </style>
    </head>
    <body>
      <main id="app" aria-label="Signals dashboard"></main>
    </body>
  </html>
`;

async function mountSignalsFixture(page) {
  const view = renderSignalsView({ signals: SAMPLE_SIGNALS, pageSize: 5 });
  await page.setContent(BASE_TEMPLATE, { waitUntil: 'domcontentloaded' });
  const metrics = await page.evaluate(
    ({ html, summary, totalSignals }) => {
      const root = document.getElementById('app');
      if (!root) {
        throw new Error('Fixture root element is missing');
      }
      const renderStart = performance.now();
      root.innerHTML = html;
      const renderDuration = performance.now() - renderStart;
      const computed = { renderDuration, summary, totalSignals };
      window.__renderMetrics = computed;
      return computed;
    },
    { html: view.html, summary: view.summary, totalSignals: view.rows.length },
  );
  return { view, metrics };
}

test.describe('@L7 dashboard signals experience', () => {
  test('[L7] renders live signals within latency budget', async ({ page }) => {
    const navigationStart = performance.now();
    const { metrics } = await mountSignalsFixture(page);
    await page.waitForSelector('.tp-live-table__body');

    const renderDuration = metrics.renderDuration;
    const totalSignals = metrics.totalSignals;
    const summary = metrics.summary;

    expect(Number.isFinite(renderDuration), 'render duration should be finite').toBe(true);
    expect(renderDuration, 'signals view should render under 1 second').toBeLessThan(1_000);
    expect(totalSignals, 'fixture should expose at least one signal').toBeGreaterThan(0);
    expect(summary?.activeCount ?? 0, 'active count should be positive').toBeGreaterThan(0);

    const navigationDuration = performance.now() - navigationStart;
    expect(navigationDuration, 'fixture navigation should complete quickly').toBeLessThan(2_000);
  });

  test('[L7] meets WCAG AA expectations via axe-core', async ({ page }) => {
    await mountSignalsFixture(page);
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(accessibilityScanResults.violations, 'no accessibility regressions are expected').toEqual([]);
    test.info().attach('axe-report', {
      body: JSON.stringify(accessibilityScanResults, null, 2),
      contentType: 'application/json',
    });
  });

  test('[L7] provides a semantic snapshot hook for CLIP-based guardrails', async ({ page }) => {
    test.skip(!SEMANTIC_GUARDRAIL_ENABLED, 'Set UI_SEMANTIC_BASELINE=true to enable CLIP semantic assertions.');

    await mountSignalsFixture(page);

    // The following block demonstrates how a semantic baseline can be enforced using
    // vision-language embeddings (e.g., CLIP). It is intentionally guarded behind an
    // opt-in flag to avoid pulling large models during routine CI runs.
    const screenshot = await page.screenshot({ fullPage: true });
    const { pipeline } = await import('@xenova/transformers');
    const clip = await pipeline('feature-extraction', 'Xenova/clip-vit-base-patch32');
    const embedding = await clip(screenshot, { pooling: 'mean', normalize: true });

    test.info().attach('semantic-embedding', {
      body: JSON.stringify(embedding.data),
      contentType: 'application/json',
    });

    test.fixme(true, 'Pending baseline integration for semantic consistency.');
  });
});
