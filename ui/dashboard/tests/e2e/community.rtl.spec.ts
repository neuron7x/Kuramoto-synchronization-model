/**
 * RTL (Right-to-Left) layout tests for Community View
 * Tests Arabic and Hebrew locale support
 */

import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { renderCommunityView } from '../../src/views/community.js';

const SAMPLE_COMMUNITY = {
  activities: [
    {
      id: 'act-1',
      type: 'contribution',
      title: 'New trading strategy shared',
      user: { name: 'John Doe', avatar: null },
      timestamp: Date.now() - 3600_000,
    },
  ],
  events: [
    {
      id: 'evt-1',
      title: 'Trading Webinar',
      date: Date.now() + 86400_000,
      location: 'Online',
    },
  ],
};

const BASE_TEMPLATE_RTL = `
  <!DOCTYPE html>
  <html lang="ar" dir="rtl">
    <head>
      <meta charset="utf-8" />
      <title>TradePulse Community</title>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        body {
          font-family: system-ui, sans-serif;
          margin: 0;
          padding: 2rem;
          background: #0f172a;
          color: #e2e8f0;
          direction: rtl;
        }
        main {
          max-width: 1200px;
          margin: 0 auto;
        }
        .tp-app {
          direction: rtl;
        }
      </style>
    </head>
    <body>
      <div class="tp-app" dir="rtl" data-locale="ar-SA">
        <main id="app" aria-label="Community dashboard"></main>
      </div>
    </body>
  </html>
`;

async function mountCommunityFixture(page: Page, rtl = true) {
  const view = renderCommunityView(SAMPLE_COMMUNITY);
  const template = rtl ? BASE_TEMPLATE_RTL : BASE_TEMPLATE_RTL.replace(/dir="rtl"/g, 'dir="ltr"').replace(/lang="ar"/g, 'lang="en"');
  
  await page.setContent(template, { waitUntil: 'domcontentloaded' });
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

test.describe('Community View RTL Support', () => {
  test('renders correctly in RTL mode', async ({ page }) => {
    await mountCommunityFixture(page, true);
    
    const app = await page.locator('.tp-app');
    const dir = await app.getAttribute('dir');
    expect(dir).toBe('rtl');
    
    const heading = await page.locator('h1, h2').first();
    await expect(heading).toBeVisible();
  });

  test('aligns text correctly in RTL', async ({ page }) => {
    await mountCommunityFixture(page, true);
    
    const textElement = await page.locator('.tp-view__title').first();
    if (textElement) {
      const textAlign = await textElement.evaluate(
        (el) => window.getComputedStyle(el).textAlign
      );
      // RTL text should be aligned right
      expect(['right', 'start']).toContain(textAlign);
    }
  });

  test('mirrors layout elements in RTL', async ({ page }) => {
    await mountCommunityFixture(page, true);
    
    // Check if navigation is on the right side
    const nav = await page.locator('[data-role="primary-nav"]').first();
    if (nav) {
      const position = await nav.boundingBox();
      const viewportWidth = page.viewportSize()?.width || 1920;
      
      // In RTL, nav should be on the right side
      expect(position?.x).toBeGreaterThan(viewportWidth / 2);
    }
  });

  test('handles long RTL text gracefully', async ({ page }) => {
    await mountCommunityFixture(page, true);
    
    // Add very long Arabic text
    await page.evaluate(() => {
      const title = document.querySelector('.tp-view__title');
      if (title) {
        title.textContent = 'هذا نص طويل جدًا بالعربية للاختبار وهو يجب أن يُعرض بشكل صحيح ومناسب في التصميم';
      }
    });
    
    const title = await page.locator('.tp-view__title').first();
    const box = await title.boundingBox();
    
    // Text should not overflow
    expect(box?.width).toBeLessThan(page.viewportSize()?.width || 1920);
  });

  test('switches between LTR and RTL dynamically', async ({ page }) => {
    await mountCommunityFixture(page, false);
    
    // Start in LTR
    let app = await page.locator('.tp-app');
    let dir = await app.getAttribute('dir');
    expect(dir).toBe('ltr');
    
    // Switch to RTL
    await page.evaluate(() => {
      const appEl = document.querySelector('.tp-app');
      if (appEl) {
        appEl.setAttribute('dir', 'rtl');
      }
    });
    
    app = await page.locator('.tp-app');
    dir = await app.getAttribute('dir');
    expect(dir).toBe('rtl');
  });

  test('preserves layout integrity in RTL', async ({ page }) => {
    await mountCommunityFixture(page, true);
    
    // Take screenshot for visual regression
    await page.screenshot({ 
      path: 'test-results/community-rtl.png',
      fullPage: true,
    });
    
    // Check that no elements overflow
    const overflowElements = await page.evaluate(() => {
      const elements = Array.from(document.querySelectorAll('*'));
      return elements.filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.right > window.innerWidth || rect.left < 0;
      }).length;
    });
    
    expect(overflowElements).toBe(0);
  });
});
