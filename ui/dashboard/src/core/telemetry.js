import { randomBytes } from 'crypto';

const TRACE_HEADER = 'traceparent';
const TELEMETRY_EVENT = 'geosync:telemetry';
const listeners = new Set();

function randomHex(bytes) {
  return randomBytes(bytes).toString('hex');
}

function emit(event) {
  const payload = { timestamp: Date.now(), ...event };
  listeners.forEach((listener) => {
    try {
      listener(payload);
    } catch (error) {
      if (typeof console !== 'undefined' && console.error) {
        console.error('Telemetry listener failed', error);
      }
    }
  });
  const target = typeof globalThis !== 'undefined' ? globalThis : null;
  if (target && typeof target.dispatchEvent === 'function') {
    try {
      const Custom = typeof target.CustomEvent === 'function' ? target.CustomEvent : null;
      const EventCtor = Custom || (typeof target.Event === 'function' ? target.Event : null);
      if (EventCtor) {
        const evt = Custom ? new Custom(TELEMETRY_EVENT, { detail: payload }) : new EventCtor(TELEMETRY_EVENT);
        if (!Custom) {
          evt.detail = payload;
        }
        target.dispatchEvent(evt);
      }
    } catch (error) {
      if (typeof console !== 'undefined' && console.debug) {
        console.debug('Telemetry dispatch fallback', error);
      }
    }
  }
  const isDevEnv = typeof process !== 'undefined' && process.env && process.env.NODE_ENV !== 'production';
  if (typeof console !== 'undefined' && console.debug && isDevEnv) {
    console.debug('[telemetry]', payload);
  }
  return payload;
}

export function onTelemetry(listener) {
  if (typeof listener === 'function') {
    listeners.add(listener);
  }
  return () => listeners.delete(listener);
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

export function recordMissingTranslation({ locale, key }) {
  return emit({ type: 'i18n.missing_translation', locale, key });
}

export function recordLocaleFallback({ requested, resolved, reason, key }) {
  return emit({ type: 'i18n.locale_fallback', requested, resolved, reason, key });
}

export function recordLocaleAdopted(locale, { source } = {}) {
  return emit({ type: 'i18n.locale_adopted', locale, source });
}

export const TRACEPARENT_HEADER = TRACE_HEADER;
