/**
 * Data source client for TradePulse Dashboard
 * Provides REST API client and WebSocket streaming capabilities
 */

const DEFAULT_BASE_URL = typeof window !== 'undefined' && window.location 
  ? `${window.location.protocol}//${window.location.host}/api`
  : 'http://localhost:8000/api';

const DEFAULT_WS_URL = typeof window !== 'undefined' && window.location
  ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/ws`
  : 'ws://localhost:8000/api/ws';

const DEFAULT_TIMEOUT = 30000; // 30 seconds
const MAX_RETRIES = 3;
const RETRY_DELAY_BASE = 1000; // 1 second
const RETRY_DELAY_MAX = 10000; // 10 seconds

/**
 * Calculate exponential backoff delay
 * @param {number} attempt - Current attempt number (0-indexed)
 * @returns {number} Delay in milliseconds
 */
function calculateBackoff(attempt) {
  const delay = Math.min(RETRY_DELAY_BASE * Math.pow(2, attempt), RETRY_DELAY_MAX);
  // Add jitter to prevent thundering herd
  return delay + Math.random() * 1000;
}

/**
 * Sleep for specified milliseconds
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise<void>}
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Fetch with timeout
 * @param {string} url - URL to fetch
 * @param {RequestInit} options - Fetch options
 * @param {number} timeout - Timeout in milliseconds
 * @returns {Promise<Response>}
 */
async function fetchWithTimeout(url, options = {}, timeout = DEFAULT_TIMEOUT) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error(`Request timeout after ${timeout}ms`);
    }
    throw error;
  }
}

/**
 * Fetch with retry logic
 * @param {string} url - URL to fetch
 * @param {RequestInit} options - Fetch options
 * @param {number} maxRetries - Maximum retry attempts
 * @returns {Promise<Response>}
 */
async function fetchWithRetry(url, options = {}, maxRetries = MAX_RETRIES) {
  let lastError;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetchWithTimeout(url, options);
      
      // Don't retry on client errors (4xx), only on server errors (5xx) and network errors
      if (response.ok || (response.status >= 400 && response.status < 500)) {
        return response;
      }
      
      lastError = new Error(`HTTP ${response.status}: ${response.statusText}`);
      
      if (attempt < maxRetries) {
        const delay = calculateBackoff(attempt);
        await sleep(delay);
      }
    } catch (error) {
      lastError = error;
      
      if (attempt < maxRetries) {
        const delay = calculateBackoff(attempt);
        await sleep(delay);
      }
    }
  }
  
  throw lastError || new Error('Request failed after retries');
}

/**
 * Data source client
 */
export class DataSourceClient {
  constructor(options = {}) {
    this.baseUrl = options.baseUrl || DEFAULT_BASE_URL;
    this.wsUrl = options.wsUrl || DEFAULT_WS_URL;
    this.timeout = options.timeout || DEFAULT_TIMEOUT;
    this.maxRetries = options.maxRetries ?? MAX_RETRIES;
    this.headers = options.headers || {};
    this._ws = null;
    this._wsListeners = new Map();
    this._wsReconnectAttempts = 0;
    this._wsMaxReconnectAttempts = 5;
    this._pendingRequests = new Map();
    this._batchQueue = [];
    this._batchTimeout = null;
    this._batchDelay = 50; // 50ms batching window
  }

  /**
   * Make a GET request to the API
   * @param {string} endpoint - API endpoint path
   * @param {object} options - Additional options
   * @returns {Promise<any>}
   */
  async get(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const fetchOptions = {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...this.headers,
        ...options.headers,
      },
    };

    const response = await fetchWithRetry(url, fetchOptions, this.maxRetries);
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Make a POST request to the API
   * @param {string} endpoint - API endpoint path
   * @param {any} data - Request body data
   * @param {object} options - Additional options
   * @returns {Promise<any>}
   */
  async post(endpoint, data, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const fetchOptions = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this.headers,
        ...options.headers,
      },
      body: JSON.stringify(data),
    };

    const response = await fetchWithRetry(url, fetchOptions, this.maxRetries);
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Fetch overview data
   * @returns {Promise<object>}
   */
  async fetchOverview() {
    return this.get('/dashboard/overview');
  }

  /**
   * Fetch positions data
   * @returns {Promise<object>}
   */
  async fetchPositions() {
    return this.get('/dashboard/positions');
  }

  /**
   * Fetch orders data
   * @returns {Promise<object>}
   */
  async fetchOrders() {
    return this.get('/dashboard/orders');
  }

  /**
   * Fetch PnL data
   * @returns {Promise<object>}
   */
  async fetchPnl() {
    return this.get('/dashboard/pnl');
  }

  /**
   * Fetch signals data
   * @returns {Promise<object>}
   */
  async fetchSignals() {
    return this.get('/dashboard/signals');
  }

  /**
   * Fetch monitoring data
   * @returns {Promise<object>}
   */
  async fetchMonitoring() {
    return this.get('/dashboard/monitoring');
  }

  /**
   * Fetch community data
   * @returns {Promise<object>}
   */
  async fetchCommunity() {
    return this.get('/dashboard/community');
  }

  /**
   * Batch multiple requests together
   * @param {Array<{endpoint: string, method?: string}>} requests - Array of requests
   * @returns {Promise<Array<any>>}
   */
  async batch(requests) {
    if (!Array.isArray(requests) || requests.length === 0) {
      return [];
    }

    // If only one request, just execute it directly
    if (requests.length === 1) {
      const req = requests[0];
      const method = (req.method || 'GET').toUpperCase();
      if (method === 'GET') {
        return [await this.get(req.endpoint, req.options)];
      }
      return [await this.post(req.endpoint, req.data, req.options)];
    }

    // Execute all requests in parallel
    return Promise.all(
      requests.map((req) => {
        const method = (req.method || 'GET').toUpperCase();
        if (method === 'GET') {
          return this.get(req.endpoint, req.options).catch((error) => ({ error: error.message }));
        }
        return this.post(req.endpoint, req.data, req.options).catch((error) => ({ error: error.message }));
      })
    );
  }

  /**
   * Connect to WebSocket
   * @returns {Promise<WebSocket>}
   */
  async connectWebSocket() {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      return this._ws;
    }

    return new Promise((resolve, reject) => {
      try {
        this._ws = new WebSocket(this.wsUrl);

        this._ws.onopen = () => {
          this._wsReconnectAttempts = 0;
          resolve(this._ws);
        };

        this._ws.onerror = (error) => {
          reject(error);
        };

        this._ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this._handleWebSocketMessage(message);
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        this._ws.onclose = () => {
          this._ws = null;
          this._handleWebSocketReconnect();
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Handle WebSocket message
   * @param {object} message - WebSocket message
   * @private
   */
  _handleWebSocketMessage(message) {
    const { type, data } = message;
    const listeners = this._wsListeners.get(type);
    
    if (listeners) {
      listeners.forEach((callback) => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in WebSocket listener for type ${type}:`, error);
        }
      });
    }
  }

  /**
   * Handle WebSocket reconnection
   * @private
   */
  async _handleWebSocketReconnect() {
    if (this._wsReconnectAttempts >= this._wsMaxReconnectAttempts) {
      console.error('WebSocket max reconnection attempts reached');
      return;
    }

    this._wsReconnectAttempts++;
    const delay = calculateBackoff(this._wsReconnectAttempts - 1);
    
    await sleep(delay);
    
    try {
      await this.connectWebSocket();
    } catch (error) {
      console.error('WebSocket reconnection failed:', error);
    }
  }

  /**
   * Subscribe to WebSocket messages
   * @param {string} type - Message type to subscribe to
   * @param {Function} callback - Callback function
   * @returns {Function} Unsubscribe function
   */
  subscribe(type, callback) {
    if (!this._wsListeners.has(type)) {
      this._wsListeners.set(type, new Set());
    }
    
    this._wsListeners.get(type).add(callback);
    
    // Ensure WebSocket is connected
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
      this.connectWebSocket().catch((error) => {
        console.error('Failed to connect WebSocket:', error);
      });
    }
    
    // Return unsubscribe function
    return () => {
      const listeners = this._wsListeners.get(type);
      if (listeners) {
        listeners.delete(callback);
        if (listeners.size === 0) {
          this._wsListeners.delete(type);
        }
      }
    };
  }

  /**
   * Stream orders in real-time
   * @param {Function} callback - Callback for order updates
   * @returns {Function} Unsubscribe function
   */
  streamOrders(callback) {
    return this.subscribe('orders', callback);
  }

  /**
   * Stream positions in real-time
   * @param {Function} callback - Callback for position updates
   * @returns {Function} Unsubscribe function
   */
  streamPositions(callback) {
    return this.subscribe('positions', callback);
  }

  /**
   * Stream PnL updates in real-time
   * @param {Function} callback - Callback for PnL updates
   * @returns {Function} Unsubscribe function
   */
  streamPnl(callback) {
    return this.subscribe('pnl', callback);
  }

  /**
   * Disconnect WebSocket
   */
  disconnect() {
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._wsListeners.clear();
    this._wsReconnectAttempts = 0;
  }

  /**
   * Check if client is connected
   * @returns {boolean}
   */
  isConnected() {
    // Check if WebSocket is available in the environment
    if (typeof WebSocket === 'undefined') {
      return false;
    }
    return this._ws && this._ws.readyState === WebSocket.OPEN;
  }
}

/**
 * Create a new data source client
 * @param {object} options - Client options
 * @returns {DataSourceClient}
 */
export function createDataSource(options = {}) {
  return new DataSourceClient(options);
}

/**
 * Default singleton instance
 */
let defaultInstance = null;

/**
 * Get default data source instance
 * @returns {DataSourceClient}
 */
export function getDataSource() {
  if (!defaultInstance) {
    defaultInstance = createDataSource();
  }
  return defaultInstance;
}

/**
 * Reset default instance (useful for testing)
 */
export function resetDataSource() {
  if (defaultInstance) {
    defaultInstance.disconnect();
    defaultInstance = null;
  }
}
