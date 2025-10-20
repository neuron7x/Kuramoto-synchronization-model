import { randomBytes } from 'crypto';

const TRACE_HEADER = 'traceparent';
const telemetrySubscribers = new Set();

function randomHex(bytes) {
  return randomBytes(bytes).toString('hex');
}

export function createTraceparent(previous) {
  if (typeof previous === 'string' && previous.trim() !== '') {
    return previous.trim();
  }
  const traceId = randomHex(16);
  const spanId = randomHex(8);
  return `00-${traceId}-${spanId}-01`;
}

export function ensureTraceHeaders(init = {}, traceparent) {
  const headers = { ...(init.headers || {}) };
  const next = createTraceparent(traceparent || headers[TRACE_HEADER]);
  headers[TRACE_HEADER] = next;
  return { ...init, headers };
}

export function extractTraceparent(headers = {}) {
  return headers[TRACE_HEADER] || null;
}

export function subscribeTelemetry(listener) {
  telemetrySubscribers.add(listener);
  return () => telemetrySubscribers.delete(listener);
}

export function recordTelemetry(event, payload = {}) {
  const entry = {
    event,
    payload: { ...payload },
    timestamp: Date.now(),
  };
  telemetrySubscribers.forEach((listener) => {
    try {
      listener(entry);
    } catch (error) {
      // eslint-disable-next-line no-console
      console.warn('telemetry listener failed', error);
    }
  });
  if (typeof globalThis !== 'undefined') {
    const store = globalThis.__TRADEPULSE_TELEMETRY__ || [];
    store.push(entry);
    globalThis.__TRADEPULSE_TELEMETRY__ = store;
  }
  return entry;
}

export function recordLocalizationFallback(details) {
  return recordTelemetry('localization.fallback', details);
}

export const TRACEPARENT_HEADER = TRACE_HEADER;
