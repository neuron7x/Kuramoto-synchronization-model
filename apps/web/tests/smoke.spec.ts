import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page as PlaywrightPage } from 'playwright-core'

test.describe('Scenario Studio smoke', () => {
  test('renders the primary dashboard layout', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/GeoSync Scenario Studio/i)
    await expect(page.getByRole('heading', { name: 'Scenario Studio' })).toBeVisible()
    await expect(page.getByLabel('Scenario template')).toBeVisible()

    await page.selectOption('#template', 'mean-reversion')
    await expect(page.getByText('Mean Reversion Swing')).toBeVisible()
  })

  test('exports scenario JSON when validation passes and disables actions when invalid', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      const writeText = async (value: string) => {
        ;(window as typeof window & { __lastCopied?: string }).__lastCopied = value
      }
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText },
        configurable: true,
      })
    })

    await page.goto('/')

    const previewLocator = page.locator('pre')
    const copyButton = page.getByRole('button', { name: 'Copy to clipboard' })
    const downloadButton = page.getByRole('button', { name: 'Download JSON' })

    await expect(copyButton).toBeEnabled()
    await expect(downloadButton).toBeEnabled()

    const preview = (await previewLocator.textContent()) ?? ''
    await copyButton.click()
    await expect(page.getByRole('status', { name: /Scenario JSON copied/ })).toBeVisible()

    const copied = await page.evaluate(
      () => (window as typeof window & { __lastCopied?: string }).__lastCopied
    )
    expect(copied).toBe(preview)

    const [download] = await Promise.all([page.waitForEvent('download'), downloadButton.click()])
    await expect(download.suggestedFilename()).toMatch(/scenario-.*\.json/)

    await page.fill('input[name="initialBalance"]', '-1')
    await expect(copyButton).toBeDisabled()
    await expect(downloadButton).toBeDisabled()
  })

  test('has no critical accessibility regressions', async ({ page }) => {
    await page.goto('/')
    const scanResults = await new AxeBuilder({ page: page as unknown as PlaywrightPage }).analyze()
    const severeViolations = scanResults.violations.filter((violation) =>
      ['critical', 'serious'].includes(violation.impact ?? '')
    )

    expect(severeViolations).toEqual([])
  })
})
