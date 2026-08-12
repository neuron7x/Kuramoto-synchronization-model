'use client'

import { useReportWebVitals } from 'next/web-vitals'

/**
 * IERD-Q6 §5 client_render instrumentation.
 *
 * Before this component the four-layer latency budget had only the
 * server_compute layer measured (the IERD-Q6 Phase-4 ENTRY gate). The
 * client_render layer (FCP < 1.0 s and the rest of the Core Web
 * Vitals) was declared in the claim but never actually captured in
 * the browser — that was the genuine debt.
 *
 * This wires Next's `useReportWebVitals` to a structured, budget-
 * classified beacon so client_render is genuinely observed. It adds
 * **zero dependencies** (Next ships `next/web-vitals`). The pure
 * helpers (`WEB_VITAL_BUDGETS_MS`, `classifyWebVital`,
 * `buildWebVitalPayload`) are exported so the contract is unit-test
 * falsifiable without a browser.
 *
 * Scope honesty: this is the *instrumentation* layer. A
 * regression-gated Lighthouse-CI budget run against a real Next build
 * (FCP < 1.0 s under headless Chrome) remains the IERD-Q6 Phase-4
 * EXIT deliverable — it needs real infra and is not faked here.
 */

export type WebVitalName = 'FCP' | 'LCP' | 'CLS' | 'INP' | 'TTFB' | 'FID'

export type WebVitalVerdict = 'within' | 'over'

/**
 * §5 budgets, in milliseconds, plus the canonical web-vitals "good"
 * thresholds for the metrics §5 does not pin numerically. CLS is
 * unitless ×1000 (0.1 → 100) so a single ms-scale table classifies
 * every metric uniformly.
 */
export const WEB_VITAL_BUDGETS_MS: Readonly<Record<WebVitalName, number>> = {
  FCP: 1000, // IERD §5: client_render FCP < 1.0 s
  TTFB: 300, // IERD §5: network_TTFB < 300 ms
  LCP: 2500, // web-vitals "good"
  INP: 200, // web-vitals "good"
  FID: 100, // web-vitals "good"
  CLS: 100, // 0.1 × 1000 — web-vitals "good"
}

/** Pure budget classification — the falsifiable core of the contract. */
export function classifyWebVital(name: WebVitalName, value: number): WebVitalVerdict {
  const budget = WEB_VITAL_BUDGETS_MS[name]
  return value <= budget ? 'within' : 'over'
}

export type WebVitalPayload = {
  name: WebVitalName
  value: number
  rating: string
  verdict: WebVitalVerdict
  id: string
  navigationType: string
}

type ReportableMetric = {
  name: string
  value: number
  rating?: string
  id: string
  navigationType?: string
}

/** Map a raw web-vitals metric to the structured, budget-tagged payload. */
export function buildWebVitalPayload(metric: ReportableMetric): WebVitalPayload {
  const name = metric.name as WebVitalName
  return {
    name,
    value: metric.value,
    rating: metric.rating ?? 'unknown',
    verdict: classifyWebVital(name, metric.value),
    id: metric.id,
    navigationType: metric.navigationType ?? 'unknown',
  }
}

const ENDPOINT = process.env.NEXT_PUBLIC_WEB_VITALS_ENDPOINT

/**
 * Forward a metric to the telemetry sink. No-ops safely when no
 * endpoint is configured or `navigator.sendBeacon` is unavailable
 * (SSR / older browsers) — instrumentation must never throw into the
 * render path.
 */
export function sendWebVital(metric: ReportableMetric): WebVitalPayload {
  const payload = buildWebVitalPayload(metric)
  if (ENDPOINT && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    try {
      navigator.sendBeacon(ENDPOINT, JSON.stringify(payload))
    } catch {
      // Telemetry is best-effort; a beacon failure must not surface.
    }
  }
  return payload
}

/** Mount once in the root layout; renders nothing. */
export function WebVitalsReporter(): null {
  useReportWebVitals((metric) => {
    sendWebVital(metric)
  })
  return null
}
