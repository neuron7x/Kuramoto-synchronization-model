import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

/**
 * IERD-Q7 §532 — Playwright route-interception specs for the edge-case
 * states that the backend-only pytest suites cannot exercise: the
 * client in-flight (`loading`), user-driven (`cancelled`), per-probe
 * `server_error`, transport `network_failure`, client `timeout`, and the
 * INV-DRO5 `simulation_diverged` recovery path.
 *
 * Each test drives the `/edge-probe` harness (which issues a *real*
 * `fetch` to the probed public endpoint) and asserts the single
 * auditable surface resolves to the correct `probe-state-<state>`. These
 * test titles are the `test_id`s registered against the previously
 * UNCOVERED cells in `tests/edge_cases/coverage_matrix.py`; the matrix
 * gate statically resolves them, so renaming a title fails the gate.
 *
 * Honesty note: every state is reached by intercepting the network
 * (`page.route`) — fulfilling 200/422/500, aborting `'failed'`, or
 * delaying past the client deadline — or by a genuine user cancel. No
 * state is faked in the component.
 */

const COLLECTION_ENDPOINTS = [
  '/features',
  '/predictions',
  '/v1/features',
  '/v1/predictions',
  '/api/v1/features',
  '/api/v1/predictions',
] as const

const COMMAND_ENDPOINT = '/admin/kill-switch'
const PROBE_ENDPOINTS = ['/health', '/metrics'] as const

function routeGlob(endpoint: string): string {
  return `**${endpoint}`
}

type Gate = { wait: Promise<void>; release: () => void }

/** A deferred promise the route handler awaits so the request stays in
 * flight until the test deterministically releases it. Definite
 * assignment keeps `release` strictly typed as a callable (the executor
 * runs synchronously inside the Promise constructor). */
function createGate(): Gate {
  let release!: () => void
  const wait = new Promise<void>((resolve) => {
    release = resolve
  })
  return { wait, release }
}

async function gotoProbe(page: Page, endpoint: string): Promise<void> {
  await page.goto(`/edge-probe?endpoint=${encodeURIComponent(endpoint)}`, {
    waitUntil: 'domcontentloaded',
  })
  await expect(page.getByTestId('endpoint-probe')).toHaveAttribute('data-endpoint', endpoint)
}

async function fulfilJson(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('IERD-Q7 edge-case probe — loading (in-flight)', () => {
  for (const endpoint of [...COLLECTION_ENDPOINTS, COMMAND_ENDPOINT]) {
    test(`shows loading while ${endpoint} is in flight`, async ({ page }) => {
      const gate = createGate()
      await page.route(routeGlob(endpoint), async (route) => {
        await gate.wait
        await fulfilJson(route, 200, { count: 1 })
      })

      await gotoProbe(page, endpoint)
      await page.getByTestId('probe-run').click()

      await expect(page.getByTestId('probe-state-loading')).toBeVisible()

      gate.release()
      await expect(page.getByTestId('probe-state-success')).toBeVisible()
    })
  }
})

test.describe('IERD-Q7 edge-case probe — cancelled (user abort)', () => {
  for (const endpoint of [...COLLECTION_ENDPOINTS, COMMAND_ENDPOINT]) {
    test(`recovers to a cancelled surface when the user aborts ${endpoint}`, async ({ page }) => {
      const gate = createGate()
      await page.route(routeGlob(endpoint), async (route) => {
        await gate.wait
        await fulfilJson(route, 200, { count: 1 })
      })

      await gotoProbe(page, endpoint)
      await page.getByTestId('probe-run').click()
      await expect(page.getByTestId('probe-state-loading')).toBeVisible()

      await page.getByTestId('probe-cancel').click()

      const cancelled = page.getByTestId('probe-state-cancelled')
      await expect(cancelled).toBeVisible()
      // §532: cancellation is a user-visible *recoverable* path.
      await expect(cancelled).toHaveAttribute('data-recoverable', 'true')
      await expect(page.getByTestId('probe-retry')).toBeVisible()

      gate.release()
    })
  }
})

test.describe('IERD-Q7 edge-case probe — server_error (per probe)', () => {
  for (const endpoint of PROBE_ENDPOINTS) {
    test(`surfaces a non-recoverable server_error for ${endpoint}`, async ({ page }) => {
      await page.route(routeGlob(endpoint), (route) =>
        fulfilJson(route, 500, { error: { code: 'internal', message: 'probe failure' } })
      )

      await gotoProbe(page, endpoint)
      await page.getByTestId('probe-run').click()

      const surface = page.getByTestId('probe-state-server_error')
      await expect(surface).toBeVisible()
      await expect(surface).toHaveAttribute('role', 'alert')
      await expect(surface).toHaveAttribute('data-recoverable', 'false')
    })
  }
})

test.describe('IERD-Q7 edge-case probe — network_failure (transport abort)', () => {
  for (const endpoint of [...COLLECTION_ENDPOINTS, COMMAND_ENDPOINT, ...PROBE_ENDPOINTS]) {
    test(`surfaces a recoverable network_failure for ${endpoint}`, async ({ page }) => {
      await page.route(routeGlob(endpoint), (route) => route.abort('failed'))

      await gotoProbe(page, endpoint)
      await page.getByTestId('probe-run').click()

      const surface = page.getByTestId('probe-state-network_failure')
      await expect(surface).toBeVisible()
      await expect(surface).toHaveAttribute('data-recoverable', 'true')
      await expect(page.getByTestId('probe-retry')).toBeVisible()
    })
  }
})

test.describe('IERD-Q7 edge-case probe — timeout (client deadline)', () => {
  for (const endpoint of [...COLLECTION_ENDPOINTS, COMMAND_ENDPOINT, ...PROBE_ENDPOINTS]) {
    test(`surfaces a recoverable timeout for ${endpoint}`, async ({ page }) => {
      // Collapse the 5s client deadline before the bundle loads so the
      // probe's AbortController fires deterministically and fast.
      await page.addInitScript(() => {
        window.__PROBE_DEADLINE_MS__ = 200
      })
      // Hang the route forever; only the client deadline can resolve it.
      await page.route(routeGlob(endpoint), () => {
        /* never fulfil */
      })

      await gotoProbe(page, endpoint)
      await page.getByTestId('probe-run').click()

      const surface = page.getByTestId('probe-state-timeout')
      await expect(surface).toBeVisible({ timeout: 15_000 })
      await expect(surface).toHaveAttribute('data-recoverable', 'true')
    })
  }
})

test.describe('IERD-Q7 edge-case probe — simulation_diverged (INV-DRO5)', () => {
  for (const endpoint of COLLECTION_ENDPOINTS) {
    test(`rejects a diverged forecast envelope with a recoverable path for ${endpoint}`, async ({
      page,
    }) => {
      await page.route(routeGlob(endpoint), (route) =>
        // A 200 body whose forecast contains a non-finite value: the
        // client INV-DRO5 guard must surface it, not render it.
        fulfilJson(route, 200, { count: 1, forecast: [1.0, 2.0, null] })
      )

      await gotoProbe(page, endpoint)
      await page.getByTestId('probe-run').click()

      const surface = page.getByTestId('probe-state-simulation_diverged')
      await expect(surface).toBeVisible()
      await expect(surface).toHaveAttribute('role', 'alert')
      // §532 / INV-DRO5: divergence has a user-visible *recoverable* path.
      await expect(surface).toHaveAttribute('data-recoverable', 'true')
      await expect(page.getByTestId('probe-retry')).toBeVisible()
    })
  }
})
