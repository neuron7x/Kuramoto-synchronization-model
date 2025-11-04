import { expect, test } from '@playwright/test'
import type { Download, Page, TestInfo } from '@playwright/test'
import { Buffer } from 'node:buffer'
import { constants as fsConstants } from 'node:fs'
import { access, mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

const NETWORK_PROFILE = {
  latency: 120,
  downloadThroughput: Math.floor((1.5 * 1024 * 1024) / 8),
  uploadThroughput: Math.floor(750_000 / 8),
}

test.beforeEach(async ({ page, browserName }) => {
  if (browserName === 'chromium') {
    const client = await page.context().newCDPSession(page)
    await client.send('Network.enable')
    await client.send('Network.emulateNetworkConditions', {
      offline: false,
      latency: NETWORK_PROFILE.latency,
      downloadThroughput: NETWORK_PROFILE.downloadThroughput,
      uploadThroughput: NETWORK_PROFILE.uploadThroughput,
    })
  }
})

async function disableAnimations(page: Page) {
  await page.addStyleTag({
    content: `* { animation-duration: 0s !important; transition-duration: 0s !important; }`,
  })
}

type ClipboardMode = 'success' | 'error' | 'none'

async function gotoScenarioStudio(
  page: Page,
  { clipboardMode }: { clipboardMode?: ClipboardMode } = {}
) {
  const mode = clipboardMode ?? 'none'
  if (mode !== 'none') {
    await page.addInitScript((shouldFail) => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          async writeText(value: string) {
            if (shouldFail) {
              throw new Error('clipboard-failure')
            }
            ;(window as typeof window & { __lastCopied?: string }).__lastCopied = value
          },
        },
      })
    }, mode === 'error')
  }

  const cacheBuster = `e2e=${Date.now().toString(36)}${Math.random().toString(16).slice(2, 6)}`
  await page.goto(`/?${cacheBuster}`, { waitUntil: 'networkidle' })
  await disableAnimations(page)
  await expect(page.getByTestId('scenario-form')).toBeVisible()
}

async function expectClipboardValue(page: Page, expected: string) {
  const actual = await page.evaluate(
    () => (window as typeof window & { __lastCopied?: string }).__lastCopied ?? ''
  )
  expect(actual).toBe(expected)
}

async function readDownload(download: Download): Promise<string> {
  const resolvedPath = await download.path()
  if (resolvedPath) {
    return readFile(resolvedPath, 'utf-8')
  }
  const stream = await download.createReadStream()
  if (!stream) {
    throw new Error('Unable to read download stream')
  }
  return new Promise<string>((resolve, reject) => {
    const chunks: Buffer[] = []
    stream.on('data', (chunk) => chunks.push(Buffer.from(chunk)))
    stream.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')))
    stream.on('error', reject)
  })
}

async function ensureVisualBaseline(page: Page, testInfo: TestInfo, fileName: string) {
  const baselinePath = testInfo.snapshotPath(fileName)
  try {
    await access(baselinePath, fsConstants.F_OK)
    return
  } catch {
    const buffer = await page.screenshot({ fullPage: true })
    await mkdir(path.dirname(baselinePath), { recursive: true })
    await writeFile(baselinePath, buffer)
    await testInfo.attach('generated-visual-baseline', {
      body: buffer,
      contentType: 'image/png',
    })
  }
}

test.describe('Critical customer journeys', () => {
  test('guides new users through onboarding choices', async ({ page }) => {
    await gotoScenarioStudio(page)

    await expect(page.getByTestId('onboarding-hero')).toContainText('Scenario Studio')
    await expect(page.getByTestId('template-description')).toContainText('Momentum Breakout')

    const notes = page.getByTestId('template-notes').locator('li')
    await expect(notes).toHaveCount(2)
    await expect(page.getByTestId('input-initialBalance')).toHaveValue('15000')
    await expect(page.getByTestId('input-riskPerTrade')).toHaveValue('1')
    await expect(page.getByTestId('input-maxPositions')).toHaveValue('3')
    await expect(page.getByTestId('input-timeframe')).toHaveValue('1h')
  })

  test('enforces authorization gates before exports', async ({ page }) => {
    await gotoScenarioStudio(page, { clipboardMode: 'success' })

    const initialInput = page.getByTestId('input-initialBalance')
    await initialInput.fill('100')
    await initialInput.blur()

    await expect(page.getByTestId('error-initialBalance')).toBeVisible()
    await expect(page.getByTestId('action-copy')).toBeDisabled()
    await expect(page.getByTestId('action-download')).toBeDisabled()

    await initialInput.fill('12000')
    await initialInput.blur()

    await expect(page.getByTestId('error-initialBalance')).toBeHidden()
    await expect(page.getByTestId('action-copy')).toBeEnabled()
    await expect(page.getByTestId('action-download')).toBeEnabled()
  })

  test('processes purchases via JSON downloads', async ({ page }) => {
    await gotoScenarioStudio(page, { clipboardMode: 'success' })

    const previewText = (await page.getByTestId('scenario-json-preview').textContent()) ?? ''

    const copyButton = page.getByTestId('action-copy')
    await copyButton.click()
    await expect(page.getByTestId('action-feedback')).toContainText('Scenario JSON copied')
    await expectClipboardValue(page, previewText.trim())

    const downloadButton = page.getByTestId('action-download')
    const [download] = await Promise.all([page.waitForEvent('download'), downloadButton.click()])
    const jsonText = await readDownload(download)
    const parsed = JSON.parse(jsonText)
    expect(parsed).toMatchObject({
      initialBalance: expect.any(Number),
      riskPerTrade: expect.any(Number),
      maxPositions: expect.any(Number),
      timeframe: expect.stringMatching(/\w+/),
    })
    await expect(page.getByTestId('action-feedback')).toContainText(
      'Scenario JSON download started.'
    )
  })

  test('allows cancellations before committing changes', async ({ page }) => {
    await gotoScenarioStudio(page)

    const riskInput = page.getByTestId('input-riskPerTrade')
    await riskInput.fill('4')
    await riskInput.blur()

    await page.getByTestId('action-reset').click()
    await expect(riskInput).toHaveValue('1')
    await expect(page.getByTestId('action-feedback')).toHaveCount(0)
  })

  test('restores template defaults when users revisit earlier choices', async ({ page }) => {
    await gotoScenarioStudio(page)

    const timeframeInput = page.getByTestId('input-timeframe')
    await page.getByTestId('template-select').selectOption('mean-reversion')
    await expect(timeframeInput).toHaveValue('4h')
    await timeframeInput.fill('2h')
    await timeframeInput.blur()

    await page.getByTestId('template-select').selectOption('momentum-breakout')
    await expect(timeframeInput).toHaveValue('1h')
    await expect(page.getByTestId('template-description')).toContainText('Momentum Breakout')
  })

  test('surfaces refunds-style messaging when exports fail and recovers on retry', async ({
    page,
  }) => {
    await gotoScenarioStudio(page, { clipboardMode: 'error' })

    const copyButton = page.getByTestId('action-copy')
    await copyButton.click()
    await expect(page.getByTestId('action-feedback')).toContainText('Failed to copy')

    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          async writeText(value: string) {
            ;(window as typeof window & { __lastCopied?: string }).__lastCopied = value
          },
        },
      })
    })

    await copyButton.click()
    await expect(page.getByTestId('action-feedback')).toContainText('Scenario JSON copied')
  })

  test('updates account-level settings such as risk guidance in real time', async ({ page }) => {
    await gotoScenarioStudio(page)

    await page.getByTestId('input-initialBalance').fill('10000')
    await page.getByTestId('input-riskPerTrade').fill('4')
    await page.getByTestId('input-maxPositions').fill('8')
    await page.getByTestId('input-timeframe').fill('2m')

    const warningList = page.getByTestId('warning-list')
    const warningCount = await warningList.locator('li').count()
    expect(warningCount).toBeGreaterThanOrEqual(2)
    await expect(page.getByTestId('timeframe-insights')).toBeVisible()

    await page.getByTestId('input-riskPerTrade').fill('1')
    await page.getByTestId('input-maxPositions').fill('3')
    await page.getByTestId('input-timeframe').fill('4h')

    await expect(page.getByTestId('warning-placeholder')).toBeVisible()
  })

  test('captures a visual regression baseline for the production-ready view', async ({ page }) => {
    const projectName = test.info().project.name
    test.skip(
      !projectName.includes('Desktop Chrome'),
      'Visual baseline captured on desktop Chromium only'
    )

    await gotoScenarioStudio(page)
    await page.getByTestId('input-initialBalance').fill('20000')
    await page.getByTestId('input-riskPerTrade').fill('1.2')
    await page.getByTestId('input-maxPositions').fill('4')
    await page.getByTestId('input-timeframe').fill('1h')

    await ensureVisualBaseline(page, test.info(), 'scenario-studio-desktop.png')
    await expect(page).toHaveScreenshot('scenario-studio-desktop.png', {
      fullPage: true,
      maxDiffPixelRatio: 0.02,
    })
  })
})
