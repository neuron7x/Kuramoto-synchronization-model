'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import LinearProgress from '@mui/material/LinearProgress'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import type { AlertColor } from '@mui/material/Alert'

/**
 * IERD-Q7 §532 — the ten edge-case states every public endpoint must
 * let the frontend render. Kept in §5 order and 1:1 with
 * ``tests/edge_cases/coverage_matrix.py::STATES``. This is the single
 * client surface that actually *issues* a request to a public endpoint
 * and resolves the in-flight / abort / transport / server outcomes that
 * the backend-only suites cannot exercise (loading, cancelled,
 * per-probe server_error, network_failure, timeout). It is consumed by
 * the Playwright route-interception specs in ``apps/web/tests`` that
 * register the previously-UNCOVERED matrix cells.
 */
export const PROBE_STATES = [
  'empty',
  'loading',
  'success',
  'validation_error',
  'server_error',
  'network_failure',
  'timeout',
  'partial_result',
  'cancelled',
  'simulation_diverged',
] as const

export type ProbeState = (typeof PROBE_STATES)[number]

type StateRender = {
  /** MUI severity → DESIGN.md §2.4 semantic token. */
  severity: AlertColor
  /** `alert` for failures (assertive), `status` for benign states. */
  role: 'alert' | 'status'
  title: string
  description: string
  /** Whether the frontend offers a user-visible recovery affordance. */
  recoverable: boolean
}

/**
 * Severity + recoverability faithful to DESIGN.md §2.4 and the Q5
 * renderer. simulation_diverged is *recoverable* and user-visible: the
 * INV-DRO5 contract says a NaN/Inf/degenerate forecast envelope must be
 * surfaced and retried, never silently rendered.
 */
const STATE_RENDER: Record<ProbeState, StateRender> = {
  empty: {
    severity: 'info',
    role: 'status',
    title: 'No results',
    description: 'The request was valid but matched no records.',
    recoverable: false,
  },
  loading: {
    severity: 'info',
    role: 'status',
    title: 'Loading',
    description: 'The request is in flight.',
    recoverable: false,
  },
  success: {
    severity: 'success',
    role: 'status',
    title: 'Success',
    description: 'The request completed and returned a result.',
    recoverable: false,
  },
  validation_error: {
    severity: 'warning',
    role: 'alert',
    title: 'Invalid request',
    description: 'The request failed validation. Correct the input and retry.',
    recoverable: true,
  },
  server_error: {
    severity: 'error',
    role: 'alert',
    title: 'Server error',
    description: 'The server failed to process the request. This is not retryable as-is.',
    recoverable: false,
  },
  network_failure: {
    severity: 'warning',
    role: 'alert',
    title: 'Network error',
    description: 'The request never reached the server. Check connectivity and retry.',
    recoverable: true,
  },
  timeout: {
    severity: 'warning',
    role: 'alert',
    title: 'Timed out',
    description: 'The request exceeded the client deadline. Retrying may succeed.',
    recoverable: true,
  },
  partial_result: {
    severity: 'warning',
    role: 'status',
    title: 'Partial results',
    description: 'A truncated page was returned; more records are available.',
    recoverable: true,
  },
  cancelled: {
    severity: 'info',
    role: 'status',
    title: 'Cancelled',
    description: 'You cancelled the request before it completed.',
    recoverable: true,
  },
  simulation_diverged: {
    severity: 'warning',
    role: 'alert',
    title: 'Simulation diverged',
    description:
      'The forecast envelope failed the INV-DRO5 stability contract (NaN/Inf/degenerate). ' +
      'It was rejected rather than rendered. Adjust inputs and retry.',
    recoverable: true,
  },
}

type ProbeBody = {
  /** Number of records the endpoint returned (collection semantics). */
  count?: number
  /** Whether more records exist beyond this page (partial semantics). */
  hasMore?: boolean
  /** Forecast envelope; non-finite values trip INV-DRO5 client-side. */
  forecast?: number[]
}

const DEFAULT_CLIENT_DEADLINE_MS = 5_000

declare global {
  interface Window {
    /** Test-only override for the client request deadline (ms). Lets the
     * Playwright timeout spec collapse the 5s deadline deterministically
     * without monkey-patching globals. */
    __PROBE_DEADLINE_MS__?: number
  }
}

function clientDeadlineMs(): number {
  const override = window.__PROBE_DEADLINE_MS__
  return typeof override === 'number' && override > 0 ? override : DEFAULT_CLIENT_DEADLINE_MS
}

function isNonFinite(value: number): boolean {
  return !Number.isFinite(value)
}

/**
 * Resolve a 200-OK body into the finer-grained collection states the
 * transport layer cannot distinguish: empty, partial_result, the
 * INV-DRO5 simulation_diverged guard, or plain success.
 */
function classifyOkBody(body: ProbeBody): ProbeState {
  if (Array.isArray(body.forecast) && body.forecast.some(isNonFinite)) {
    return 'simulation_diverged'
  }
  if (typeof body.count === 'number' && body.count === 0) {
    return 'empty'
  }
  if (body.hasMore === true) {
    return 'partial_result'
  }
  return 'success'
}

export type EndpointProbeProps = {
  /** Public endpoint path to probe, e.g. ``/health`` or ``/features``. */
  endpoint: string
}

/**
 * Issues a real ``fetch`` against ``endpoint`` and renders the resolved
 * edge-case state through one auditable surface. Every terminal state
 * is reachable deterministically from a Playwright ``page.route``
 * handler (fulfil 200/422/500, abort 'failed', or a delayed route that
 * outlives the client deadline), and the in-flight ``loading`` and the
 * user-driven ``cancelled`` states are genuine client behaviours, not
 * mocks.
 */
export function EndpointProbe({ endpoint }: EndpointProbeProps) {
  const [state, setState] = useState<ProbeState | 'idle'>('idle')
  const [message, setMessage] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  const run = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setMessage(null)
    setState('loading')

    const deadline = window.setTimeout(
      () => controller.abort(new DOMException('timeout', 'TimeoutError')),
      clientDeadlineMs()
    )

    try {
      const response = await fetch(endpoint, {
        method: 'GET',
        signal: controller.signal,
        cache: 'no-store',
      })
      window.clearTimeout(deadline)

      if (response.status === 422) {
        let detail = STATE_RENDER.validation_error.description
        try {
          const body = (await response.json()) as { error?: { message?: string } }
          if (body.error?.message) {
            detail = body.error.message
          }
        } catch {
          // keep default copy
        }
        setMessage(detail)
        setState('validation_error')
        return
      }

      if (response.status >= 500) {
        setState('server_error')
        return
      }

      if (!response.ok) {
        setState('validation_error')
        return
      }

      let body: ProbeBody = {}
      try {
        body = (await response.json()) as ProbeBody
      } catch {
        // empty / non-JSON probe body → treat as plain success
      }
      setState(classifyOkBody(body))
    } catch (error) {
      window.clearTimeout(deadline)
      if (error instanceof DOMException && error.name === 'TimeoutError') {
        setState('timeout')
        return
      }
      if (controller.signal.aborted) {
        // Distinguish a user cancel (TimeoutError already handled above)
        // from a transport-level failure surfaced as an AbortError.
        if (error instanceof DOMException && error.name === 'AbortError') {
          setState('cancelled')
          return
        }
      }
      setState('network_failure')
    }
  }, [endpoint])

  const cancel = useCallback(() => {
    controllerRef.current?.abort(new DOMException('cancelled', 'AbortError'))
  }, [])

  useEffect(() => {
    return () => {
      controllerRef.current?.abort(new DOMException('unmount', 'AbortError'))
    }
  }, [])

  return (
    <Box data-testid="endpoint-probe" data-endpoint={endpoint}>
      <Stack spacing={2}>
        <Typography variant="h5" component="h1" data-testid="probe-title">
          Edge-case probe: {endpoint}
        </Typography>
        <Stack direction="row" spacing={2}>
          <Button variant="contained" onClick={run} data-testid="probe-run">
            Probe endpoint
          </Button>
          <Button variant="outlined" onClick={cancel} data-testid="probe-cancel">
            Cancel
          </Button>
        </Stack>

        {state === 'idle' ? (
          <Typography variant="body2" color="text.secondary" data-testid="probe-idle">
            Press “Probe endpoint” to issue a request.
          </Typography>
        ) : state === 'loading' ? (
          <Box role="status" aria-busy="true" data-testid="probe-state-loading">
            <Typography variant="body2" color="text.secondary">
              Requesting {endpoint}…
            </Typography>
            <LinearProgress aria-label="Probe request in flight" />
          </Box>
        ) : (
          <Alert
            severity={STATE_RENDER[state].severity}
            role={STATE_RENDER[state].role}
            data-testid={`probe-state-${state}`}
            data-recoverable={STATE_RENDER[state].recoverable ? 'true' : 'false'}
          >
            <AlertTitle>{STATE_RENDER[state].title}</AlertTitle>
            {message ?? STATE_RENDER[state].description}
          </Alert>
        )}

        {state !== 'idle' && state !== 'loading' && STATE_RENDER[state].recoverable ? (
          <Button variant="text" onClick={run} data-testid="probe-retry">
            Retry
          </Button>
        ) : null}
      </Stack>
    </Box>
  )
}
