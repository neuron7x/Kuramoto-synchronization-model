import { expect, test } from '@playwright/test'

test.describe('Scenario health analytics', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.addStyleTag({
      content: '* { transition-duration: 0s !important; animation-duration: 0s !important; }',
    })
    await expect(page.getByTestId('scenario-form')).toBeVisible()
  })

  test('downgrades health status when risk becomes excessive', async ({ page }) => {
    const statusChip = page.getByTestId('health-status')

    await expect(statusChip).toContainText('Production-ready')

    await page.getByTestId('input-initialBalance').fill('1000')
    await page.getByTestId('input-riskPerTrade').fill('4')
    await page.getByTestId('input-maxPositions').fill('8')
    await page.getByTestId('input-timeframe').fill('2m')

    await page.getByTestId('input-timeframe').blur()

    await expect(page.getByTestId('warning-list')).toBeVisible()
    await expect(statusChip).toContainText('High risk')
    await expect(page.getByTestId('health-score')).toContainText('20 / 100')
  })

  test('signals validation issues when inputs become invalid', async ({ page }) => {
    const timeframeInput = page.getByTestId('input-timeframe')
    await timeframeInput.fill('invalid')
    await timeframeInput.blur()

    await expect(page.getByTestId('error-timeframe')).toBeVisible()
    await expect(page.getByTestId('health-status')).toContainText('Resolve errors')
    await expect(page.getByTestId('health-meter')).toHaveAttribute('aria-valuenow', '25')

    await timeframeInput.fill('1h')
    await timeframeInput.blur()

    await expect(page.getByTestId('error-timeframe')).toHaveCount(0)
    await expect(page.getByTestId('health-status')).toContainText('Production-ready')
  })
})
