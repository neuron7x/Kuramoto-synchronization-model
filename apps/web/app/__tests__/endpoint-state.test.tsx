import { render, screen } from '@testing-library/react'

import { EndpointState, UX_STATES, type UxState } from '../(protected)/_components/endpoint-state'
import { AppThemeProvider } from '../providers'

function renderState(state: UxState, message?: string) {
  return render(
    <AppThemeProvider>
      <EndpointState state={state} message={message} />
    </AppThemeProvider>
  )
}

describe('EndpointState — IERD-Q5 §5 six-state renderer', () => {
  test('mirrors the backend REQUIRED_STATES contract exactly', () => {
    // 1:1 with tests/api/test_ux_state_coverage.py::REQUIRED_STATES.
    expect([...UX_STATES]).toEqual([
      'success',
      'empty',
      'partial',
      'validation_error',
      'server_error',
      'timeout',
    ])
  })

  test.each(UX_STATES)('renders a dedicated, distinct surface for "%s"', (state) => {
    renderState(state)
    const node = screen.getByTestId(`endpoint-state-${state}`)
    expect(node).toBeInTheDocument()
    // Non-empty default copy → no blank state ever reaches the user.
    expect(node.textContent?.trim().length ?? 0).toBeGreaterThan(0)
  })

  test('every declared state is covered by the renderer (UXRS = 1.0)', () => {
    const { container } = render(
      <AppThemeProvider>
        <>
          {UX_STATES.map((state) => (
            <EndpointState key={state} state={state} />
          ))}
        </>
      </AppThemeProvider>
    )
    const rendered = container.querySelectorAll('[data-testid^="endpoint-state-"]')
    expect(rendered).toHaveLength(UX_STATES.length)
  })

  test('failure states are assertive (role=alert), benign states are status', () => {
    renderState('server_error')
    expect(screen.getByTestId('endpoint-state-server_error')).toHaveAttribute('role', 'alert')
    renderState('success')
    expect(screen.getByTestId('endpoint-state-success')).toHaveAttribute('role', 'status')
  })

  test('recoverable flag matches the contract (timeout retryable, server_error not)', () => {
    renderState('timeout')
    expect(screen.getByTestId('endpoint-state-timeout')).toHaveAttribute('data-recoverable', 'true')
    renderState('server_error')
    expect(screen.getByTestId('endpoint-state-server_error')).toHaveAttribute(
      'data-recoverable',
      'false'
    )
  })

  test('a server-supplied message overrides the default description', () => {
    renderState('timeout', 'Deadline of 30s exceeded')
    expect(screen.getByTestId('endpoint-state-timeout')).toHaveTextContent(
      'Deadline of 30s exceeded'
    )
  })
})
