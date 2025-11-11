import { ensureTraceHeaders, createTraceparent } from '../core/telemetry.js';

const ROUTE_ENDPOINTS = {
  overview: '/dashboard/overview',
  monitoring: '/dashboard/monitoring',
  positions: '/dashboard/positions',
  orders: '/dashboard/orders',
  pnl: '/dashboard/pnl',
  signals: '/dashboard/signals',
  community: '/dashboard/community',
};

function normaliseBaseUrl(baseUrl = '/') {
  if (typeof baseUrl !== 'string' || baseUrl.trim() === '') {
    return '/';
  }
  const trimmed = baseUrl.trim();
  if (trimmed.endsWith('/')) {
    return trimmed.slice(0, -1);
  }
  return trimmed;
}

function toAbsoluteUrl(path, baseUrl) {
  try {
    return new URL(path, baseUrl).toString();
  } catch (error) {
    const base = normaliseBaseUrl(baseUrl);
    if (path.startsWith('/')) {
      return `${base}${path}`;
    }
    return `${base}/${path}`;
  }
}

function toWebSocketUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'https:') {
      parsed.protocol = 'wss:';
    } else if (parsed.protocol === 'http:') {
      parsed.protocol = 'ws:';
    }
    return parsed.toString();
  } catch (error) {
    return url;
  }
}

export class DashboardDataClient {
  constructor({
    baseUrl = '/',
    fetchImpl,
    WebSocketImpl,
    streamPath = '/dashboard/stream',
    streamUrl,
    requestInit = {},
  } = {}) {
    this.baseUrl = normaliseBaseUrl(baseUrl);
    this.fetchImpl = fetchImpl || (typeof fetch === 'function' ? fetch.bind(globalThis) : null);
    if (!this.fetchImpl) {
      throw new Error('DashboardDataClient requires a fetch implementation');
    }
    this.WebSocketImpl = WebSocketImpl || (typeof WebSocket === 'function' ? WebSocket : null);
    this.streamPath = streamPath;
    this.streamUrl = streamUrl || null;
    this.requestInit = {
      headers: { Accept: 'application/json' },
      ...requestInit,
    };
  }

  _buildUrl(path) {
    const endpoint = typeof path === 'string' && path.trim() !== '' ? path : '/';
    return toAbsoluteUrl(endpoint, this.baseUrl || (typeof window !== 'undefined' ? window.location?.origin || '/' : '/'));
  }

  _buildStreamUrl() {
    if (this.streamUrl) {
      return this.streamUrl;
    }
    return toWebSocketUrl(this._buildUrl(this.streamPath));
  }

  async _request(path, init = {}) {
    const url = this._buildUrl(path);
    const traceparent = createTraceparent(init.headers?.traceparent || init.headers?.Traceparent);
    const options = ensureTraceHeaders({ ...this.requestInit, ...init }, traceparent);
    const response = await this.fetchImpl(url, options);
    if (!response.ok) {
      let detail = '';
      try {
        detail = await response.text();
      } catch (error) {
        detail = '';
      }
      const message = detail ? `${response.status} ${response.statusText}: ${detail}` : `${response.status} ${response.statusText}`;
      throw new Error(`Dashboard request failed: ${message}`);
    }
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return response.json();
    }
    return response.text();
  }

  async fetchSnapshot() {
    return this._request('/dashboard/snapshot');
  }

  async fetchRoute(route) {
    const endpoint = ROUTE_ENDPOINTS[route];
    if (!endpoint) {
      throw new Error(`Unknown dashboard route: ${route}`);
    }
    const payload = await this._request(endpoint);
    return { route, payload };
  }

  subscribe(handlers = {}) {
    if (!this.WebSocketImpl) {
      return { close: () => {}, socket: null };
    }
    const url = this._buildStreamUrl();
    const socket = new this.WebSocketImpl(url);

    const safeCall = (callback, ...args) => {
      if (typeof callback === 'function') {
        try {
          callback(...args);
        } catch (error) {
          if (typeof console !== 'undefined' && console.error) {
            console.error('Dashboard stream handler failed', error);
          }
        }
      }
    };

    socket.onopen = (event) => {
      safeCall(handlers.open, event);
    };

    socket.onerror = (event) => {
      safeCall(handlers.error, event);
    };

    socket.onclose = (event) => {
      safeCall(handlers.close, event);
    };

    socket.onmessage = (event) => {
      let payload = event.data;
      try {
        if (typeof payload === 'string') {
          payload = JSON.parse(payload);
        }
      } catch (error) {
        safeCall(handlers.error, error);
        return;
      }
      const message = payload && typeof payload === 'object' ? payload : { type: 'message', payload };
      const type = message.type || message.route || 'message';
      const data = Object.prototype.hasOwnProperty.call(message, 'payload') ? message.payload : message.data ?? message;
      const handler = handlers[type] || handlers.message;
      safeCall(handler, data, message);
    };

    const close = () => {
      try {
        if (socket.readyState === socket.OPEN || socket.readyState === socket.CONNECTING) {
          socket.close();
        }
      } catch (error) {
        // Ignore teardown errors
      }
    };

    return { socket, close };
  }
}

export default DashboardDataClient;
