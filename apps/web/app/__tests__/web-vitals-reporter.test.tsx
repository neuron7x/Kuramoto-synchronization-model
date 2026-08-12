import { render } from '@testing-library/react'

import {
  WEB_VITAL_BUDGETS_MS,
  WebVitalsReporter,
  buildWebVitalPayload,
  classifyWebVital,
  sendWebVital,
} from '../_components/web-vitals-reporter'

// Capture the callback Next would invoke per metric.
let capturedReporter: ((metric: unknown) => void) | null = null
jest.mock('next/web-vitals', () => ({
  useReportWebVitals: (fn: (metric: unknown) => void) => {
    capturedReporter = fn
  },
}))

describe('WebVitalsReporter — IERD-Q6 §5 client_render instrumentation', () => {
  beforeEach(() => {
    capturedReporter = null
  })

  test('budget table pins the IERD §5 numbers verbatim', () => {
    // FCP < 1.0 s and TTFB < 300 ms are the §5 hard budgets; a drift
    // here is a silent contract regression.
    expect(WEB_VITAL_BUDGETS_MS.FCP).toBe(1000)
    expect(WEB_VITAL_BUDGETS_MS.TTFB).toBe(300)
  })

  test('classifyWebVital is a correct, falsifiable budget gate', () => {
    expect(classifyWebVital('FCP', 800)).toBe('within')
    expect(classifyWebVital('FCP', 1000)).toBe('within') // boundary inclusive
    expect(classifyWebVital('FCP', 1200)).toBe('over')
    expect(classifyWebVital('TTFB', 299)).toBe('within')
    expect(classifyWebVital('TTFB', 301)).toBe('over')
  })

  test('buildWebVitalPayload tags the metric with its budget verdict', () => {
    const payload = buildWebVitalPayload({
      name: 'FCP',
      value: 1234,
      rating: 'poor',
      id: 'v1-fcp-1',
      navigationType: 'navigate',
    })
    expect(payload).toEqual({
      name: 'FCP',
      value: 1234,
      rating: 'poor',
      verdict: 'over',
      id: 'v1-fcp-1',
      navigationType: 'navigate',
    })
  })

  test('sendWebVital is a safe no-op when no endpoint is configured', () => {
    // NEXT_PUBLIC_WEB_VITALS_ENDPOINT is unset in the test env → must
    // not throw and must still return the classified payload.
    const payload = sendWebVital({ name: 'LCP', value: 1800, id: 'lcp-1' })
    expect(payload.name).toBe('LCP')
    expect(payload.verdict).toBe('within')
  })

  test('the component registers the Next web-vitals hook and renders nothing', () => {
    const { container } = render(<WebVitalsReporter />)
    expect(container).toBeEmptyDOMElement()
    expect(typeof capturedReporter).toBe('function')
    // Driving the captured callback must not throw.
    expect(() => capturedReporter?.({ name: 'CLS', value: 50, id: 'cls-1' })).not.toThrow()
  })
})
