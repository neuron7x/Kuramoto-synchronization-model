'use client'

import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import type { AlertColor } from '@mui/material/Alert'

/**
 * IERD-Q5 §5 — the six UX states every endpoint must let the frontend
 * render. Kept in §5 order and mirrored 1:1 with the backend contract
 * (`REQUIRED_STATES` in tests/api/test_ux_state_coverage.py). The
 * OpenAPI gate proves the API exposes each state; this component is
 * the single renderer that turns each into a dignified, accessible
 * surface so the frontend never invents an ad-hoc state UI.
 */
export const UX_STATES = [
  'success',
  'empty',
  'partial',
  'validation_error',
  'server_error',
  'timeout',
] as const

export type UxState = (typeof UX_STATES)[number]

type StateRender = {
  /** MUI severity → DESIGN.md §2.4 semantic token. */
  severity: AlertColor
  /** `alert` for failures (assertive), `status` for benign states. */
  role: 'alert' | 'status'
  title: string
  description: string
  /** Whether the frontend should offer a retry affordance. */
  recoverable: boolean
}

/**
 * Severity mapping is faithful to DESIGN.md §2.4 (signals used
 * sparingly): a recoverable client/transport condition is `warning`
 * (caution), an unrecoverable server fault is `error` (negative), a
 * benign empty result is `info` (neutral), a fulfilled request is
 * `success` (positive). Timeout and validation_error are recoverable;
 * server_error is not.
 */
const STATE_RENDER: Record<UxState, StateRender> = {
  success: {
    severity: 'success',
    role: 'status',
    title: 'Success',
    description: 'The request completed and returned a result.',
    recoverable: false,
  },
  empty: {
    severity: 'info',
    role: 'status',
    title: 'No results',
    description: 'The request was valid but matched no records.',
    recoverable: false,
  },
  partial: {
    severity: 'warning',
    role: 'status',
    title: 'Partial results',
    description: 'A truncated page was returned; more records are available.',
    recoverable: true,
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
  timeout: {
    severity: 'warning',
    role: 'alert',
    title: 'Timed out',
    description: 'The request exceeded the server deadline. Retrying may succeed.',
    recoverable: true,
  },
}

export type EndpointStateProps = {
  state: UxState
  /** Optional server-supplied message (e.g. ErrorResponse.error.message). */
  message?: string
}

/**
 * Single source of truth for rendering an endpoint's UX state. Every
 * state resolves through this one path so the IERD-Q5 §5 contract
 * ("frontend rendering for every declared state") holds by
 * construction rather than by scattered ad-hoc handling.
 */
export function EndpointState({ state, message }: EndpointStateProps) {
  const render = STATE_RENDER[state]
  return (
    <Alert
      severity={render.severity}
      role={render.role}
      data-testid={`endpoint-state-${state}`}
      data-recoverable={render.recoverable ? 'true' : 'false'}
    >
      <AlertTitle>{render.title}</AlertTitle>
      {message ?? render.description}
    </Alert>
  )
}
