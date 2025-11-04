import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ProtectedHomePage from '../(protected)/page'
import { AppThemeProvider } from '../providers'

function renderHome() {
  return render(
    <AppThemeProvider>
      <ProtectedHomePage />
    </AppThemeProvider>
  )
}

describe('Scenario Studio home page', () => {
  test('renders default template with health summary and preview', async () => {
    renderHome()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Scenario Studio' })).toBeInTheDocument()
    })

    const templateSelect = screen.getByTestId('template-select') as HTMLSelectElement
    expect(templateSelect.value).toBe('momentum-breakout')

    expect(screen.getByTestId('input-initialBalance')).toHaveDisplayValue('15000')
    expect(screen.getByTestId('input-riskPerTrade')).toHaveDisplayValue('1')
    expect(screen.getByTestId('input-maxPositions')).toHaveDisplayValue('3')
    expect(screen.getByTestId('input-timeframe')).toHaveDisplayValue('1h')

    expect(screen.getByTestId('health-status')).toHaveTextContent('Production-ready')
    expect(screen.getByTestId('health-summary')).toHaveTextContent('Risk controls look balanced')

    const preview = screen.getByTestId('scenario-json-preview')
    expect(preview.textContent).toContain('"initialBalance": 15000')
    expect(preview.textContent).toContain('"timeframe": "1h"')
  })

  test('switching templates resets form values to the selected defaults', async () => {
    const user = userEvent.setup()
    renderHome()

    const templateSelect = screen.getByTestId('template-select')
    const timeframeInput = screen.getByTestId('input-timeframe') as HTMLInputElement

    await user.selectOptions(templateSelect, 'mean-reversion')
    expect(timeframeInput).toHaveValue('4h')

    await user.clear(timeframeInput)
    await user.type(timeframeInput, '2h')
    expect(timeframeInput).toHaveValue('2h')

    await user.selectOptions(templateSelect, 'momentum-breakout')
    expect(timeframeInput).toHaveValue('1h')

    const notes = within(screen.getByTestId('template-notes')).getAllByRole('listitem')
    expect(notes).toHaveLength(2)
  })

  test('disables export actions and surfaces field errors when validation fails', async () => {
    const user = userEvent.setup()
    renderHome()

    const balanceInput = screen.getByTestId('input-initialBalance') as HTMLInputElement

    await user.clear(balanceInput)
    await user.type(balanceInput, '-50')
    await user.tab()

    const errorMessage = await screen.findByTestId('error-initialBalance')
    expect(errorMessage).toHaveTextContent('Enter a positive starting balance')
    expect(screen.getByTestId('action-copy')).toBeDisabled()
    expect(screen.getByTestId('action-download')).toBeDisabled()

    await user.clear(balanceInput)
    await user.type(balanceInput, '5000')
    await user.tab()

    expect(screen.queryByTestId('error-initialBalance')).not.toBeInTheDocument()
    expect(screen.getByTestId('action-copy')).toBeEnabled()
    expect(screen.getByTestId('action-download')).toBeEnabled()
  })

  test('copies the scenario JSON to the clipboard on demand', async () => {
    if (!window.navigator.clipboard) {
      Object.defineProperty(window.navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: async () => Promise.resolve(),
        },
      })
    }

    const writeText = jest.fn().mockResolvedValue(undefined)
    const clipboard = window.navigator.clipboard as unknown as {
      writeText: typeof writeText
    }
    clipboard.writeText = writeText

    const user = userEvent.setup()
    renderHome()

    await user.click(screen.getByTestId('action-copy'))

    const feedback = await screen.findByTestId('action-feedback')
    expect(feedback).toHaveTextContent('Scenario JSON copied to clipboard.')
  })
})
