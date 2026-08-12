'use client'

import { useSearchParams } from 'next/navigation'

import { EndpointProbe } from './endpoint-probe'

/** Allow-list of public endpoint paths the harness may probe. Mirrors the
 * gated public operations scored by ``tests/edge_cases/coverage_matrix.py``;
 * an unknown ``endpoint`` query falls back to ``/health`` so the harness can
 * never be coerced into probing an arbitrary origin path. */
const PROBE_ENDPOINTS = new Set<string>([
  '/health',
  '/metrics',
  '/features',
  '/predictions',
  '/v1/features',
  '/v1/predictions',
  '/api/v1/features',
  '/api/v1/predictions',
  '/admin/kill-switch',
])

const DEFAULT_ENDPOINT = '/health'

export function EdgeProbeClient() {
  const params = useSearchParams()
  const requested = params?.get('endpoint') ?? DEFAULT_ENDPOINT
  const endpoint = PROBE_ENDPOINTS.has(requested) ? requested : DEFAULT_ENDPOINT
  return <EndpointProbe endpoint={endpoint} />
}
