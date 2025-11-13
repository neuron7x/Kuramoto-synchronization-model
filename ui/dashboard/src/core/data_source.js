/**
 * Data source module for TradePulse Dashboard
 * Provides REST/WebSocket client for live backend integration
 * with retry, batching, and error handling
 */

const DEFAULT_BASE_URL = '/api/v1';
const DEFAULT_WS_URL = 'ws://localhost:8080/ws';
const DEFAULT_RETRY_ATTEMPTS = 3;
const DEFAULT_RETRY_DELAY = 1000;
const DEFAULT_BATCH_SIZE = 50;
const DEFAULT_BATCH_DELAY = 100;

/**
 * REST API client with retry logic
 */
class RestClient {
  constructor({ baseUrl = DEFAULT_BASE_URL, retryAttempts = DEFAULT_RETRY_ATTEMPTS, retryDelay = DEFAULT_RETRY_DELAY } = {}) {
    this.baseUrl = baseUrl;
    this.retryAttempts = retryAttempts;
    this.retryDelay = retryDelay;
  }

  async fetch(endpoint, options = {}, attempt = 0) {
    const url = `${this.baseUrl}${endpoint}`;
    
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
        ...options,
      });

      if (!response.ok) {
        const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
        error.status = response.status;
        error.response = response;
        throw error;
      }

      return await response.json();
    } catch (error) {
      if (attempt < this.retryAttempts) {
        await new Promise((resolve) => setTimeout(resolve, this.retryDelay * Math.pow(2, attempt)));
        return this.fetch(endpoint, options, attempt + 1);
      }
      throw error;
    }
  }

  async get(endpoint, options = {}) {
    return this.fetch(endpoint, { ...options, method: 'GET' });
  }

  async post(endpoint, data, options = {}) {
    return this.fetch(endpoint, {
      ...options,
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async put(endpoint, data, options = {}) {
    return this.fetch(endpoint, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async delete(endpoint, options = {}) {
    return this.fetch(endpoint, { ...options, method: 'DELETE' });
  }
}

/**
 * WebSocket client for streaming data
 */
class WebSocketClient {
  constructor({ url = DEFAULT_WS_URL, reconnect = true, reconnectDelay = 3000 } = {}) {
    this.url = url;
    this.reconnect = reconnect;
    this.reconnectDelay = reconnectDelay;
    this.ws = null;
    this.listeners = new Map();
    this.reconnectTimer = null;
    this.isConnecting = false;
    this.isClosed = false;
  }

  connect() {
    if (this.ws || this.isConnecting) {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      this.isConnecting = true;
      
      try {
        this.ws = new WebSocket(this.url);

        this.ws.addEventListener('open', () => {
          this.isConnecting = false;
          this.emit('connect', {});
          resolve();
        });

        this.ws.addEventListener('message', (event) => {
          try {
            const data = JSON.parse(event.data);
            this.emit('message', data);
            
            if (data.type) {
              this.emit(data.type, data.payload || data);
            }
          } catch (error) {
            this.emit('error', { error, raw: event.data });
          }
        });

        this.ws.addEventListener('error', (error) => {
          this.isConnecting = false;
          this.emit('error', error);
          reject(error);
        });

        this.ws.addEventListener('close', () => {
          this.isConnecting = false;
          this.ws = null;
          this.emit('disconnect', {});
          
          if (this.reconnect && !this.isClosed) {
            this.scheduleReconnect();
          }
        });
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  scheduleReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.isClosed) {
        this.connect().catch(() => {
          // Reconnection failed, will retry
        });
      }
    }, this.reconnectDelay);
  }

  send(type, payload) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }

    const message = JSON.stringify({ type, payload, timestamp: Date.now() });
    this.ws.send(message);
  }

  on(event, handler) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event).add(handler);
  }

  off(event, handler) {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  emit(event, data) {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (error) {
          console.error('Error in event handler:', error);
        }
      });
    }
  }

  close() {
    this.isClosed = true;
    this.reconnect = false;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.listeners.clear();
  }
}

/**
 * Request batcher for optimizing multiple requests
 */
class RequestBatcher {
  constructor({ batchSize = DEFAULT_BATCH_SIZE, batchDelay = DEFAULT_BATCH_DELAY, executor } = {}) {
    this.batchSize = batchSize;
    this.batchDelay = batchDelay;
    this.executor = executor;
    this.queue = [];
    this.timer = null;
  }

  add(request) {
    return new Promise((resolve, reject) => {
      this.queue.push({ request, resolve, reject });

      if (this.queue.length >= this.batchSize) {
        this.flush();
      } else if (!this.timer) {
        this.timer = setTimeout(() => this.flush(), this.batchDelay);
      }
    });
  }

  async flush() {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    if (this.queue.length === 0) {
      return;
    }

    const batch = this.queue.splice(0, this.queue.length);

    try {
      const results = await this.executor(batch.map((item) => item.request));
      
      batch.forEach((item, index) => {
        item.resolve(results[index]);
      });
    } catch (error) {
      batch.forEach((item) => {
        item.reject(error);
      });
    }
  }
}

/**
 * Main data source for TradePulse Dashboard
 */
export class DataSource {
  constructor(config = {}) {
    this.rest = new RestClient(config.rest || {});
    this.ws = new WebSocketClient(config.ws || {});
    this.batcher = new RequestBatcher({
      ...config.batch,
      executor: (requests) => this.rest.post('/batch', { requests }),
    });
  }

  // Overview data
  async fetchOverview() {
    return this.rest.get('/dashboard/overview');
  }

  // Orders data
  async fetchOrders(filters = {}) {
    const query = new URLSearchParams(filters).toString();
    return this.rest.get(`/orders${query ? `?${query}` : ''}`);
  }

  async fetchOrder(orderId) {
    return this.rest.get(`/orders/${orderId}`);
  }

  async cancelOrder(orderId) {
    return this.rest.post(`/orders/${orderId}/cancel`);
  }

  async retryOrder(orderId) {
    return this.rest.post(`/orders/${orderId}/retry`);
  }

  // Positions data
  async fetchPositions(filters = {}) {
    const query = new URLSearchParams(filters).toString();
    return this.rest.get(`/positions${query ? `?${query}` : ''}`);
  }

  // Signals data
  async fetchSignals(filters = {}) {
    const query = new URLSearchParams(filters).toString();
    return this.rest.get(`/signals${query ? `?${query}` : ''}`);
  }

  // Monitoring data
  async fetchMonitoring(timeframe = '1h') {
    return this.rest.get(`/monitoring?timeframe=${timeframe}`);
  }

  // PnL data
  async fetchPnl({ strategies = [], timeframe = '1d', kpi = [] } = {}) {
    const params = new URLSearchParams();
    strategies.forEach((s) => params.append('strategy', s));
    if (timeframe) params.set('timeframe', timeframe);
    kpi.forEach((k) => params.append('kpi', k));
    return this.rest.get(`/pnl?${params.toString()}`);
  }

  // Community data
  async fetchCommunity(filters = {}) {
    const query = new URLSearchParams(filters).toString();
    return this.rest.get(`/community${query ? `?${query}` : ''}`);
  }

  // Onboarding data
  async fetchOnboardingProgress(userId) {
    return this.rest.get(`/onboarding/progress/${userId}`);
  }

  async saveOnboardingProgress(userId, progress) {
    return this.rest.put(`/onboarding/progress/${userId}`, progress);
  }

  // Streaming orders
  streamOrders(handler) {
    this.ws.on('order', handler);
    this.ws.send('subscribe', { channel: 'orders' });
    
    return () => {
      this.ws.off('order', handler);
      this.ws.send('unsubscribe', { channel: 'orders' });
    };
  }

  // Streaming positions
  streamPositions(handler) {
    this.ws.on('position', handler);
    this.ws.send('subscribe', { channel: 'positions' });
    
    return () => {
      this.ws.off('position', handler);
      this.ws.send('unsubscribe', { channel: 'positions' });
    };
  }

  // Streaming signals
  streamSignals(handler) {
    this.ws.on('signal', handler);
    this.ws.send('subscribe', { channel: 'signals' });
    
    return () => {
      this.ws.off('signal', handler);
      this.ws.send('unsubscribe', { channel: 'signals' });
    };
  }

  // Connect WebSocket
  async connect() {
    return this.ws.connect();
  }

  // Disconnect WebSocket
  disconnect() {
    this.ws.close();
  }

  // Handle connection events
  onConnect(handler) {
    this.ws.on('connect', handler);
  }

  onDisconnect(handler) {
    this.ws.on('disconnect', handler);
  }

  onError(handler) {
    this.ws.on('error', handler);
  }
}

// Export singleton instance
let defaultInstance = null;

export function getDataSource(config) {
  if (!defaultInstance) {
    defaultInstance = new DataSource(config);
  }
  return defaultInstance;
}

export function resetDataSource() {
  if (defaultInstance) {
    defaultInstance.disconnect();
    defaultInstance = null;
  }
}
