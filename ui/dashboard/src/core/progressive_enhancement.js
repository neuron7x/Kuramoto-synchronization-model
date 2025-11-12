/**
 * Progressive enhancement script for TradePulse Dashboard
 * Handles client-side data loading, real-time updates, and error handling
 */

import { getDataSource } from './data_source.js';

/**
 * Toast notification system
 */
class ToastManager {
  constructor() {
    this.container = null;
    this.toasts = new Map();
    this.toastIdCounter = 0;
  }

  /**
   * Initialize toast container
   */
  init() {
    if (typeof document === 'undefined') {
      return;
    }

    if (!this.container) {
      this.container = document.createElement('div');
      this.container.className = 'tp-toast-container';
      this.container.setAttribute('role', 'region');
      this.container.setAttribute('aria-label', 'Notifications');
      document.body.appendChild(this.container);
    }
  }

  /**
   * Show a toast notification
   * @param {object} options - Toast options
   * @param {string} options.message - Toast message
   * @param {string} options.type - Toast type (info, success, warning, error)
   * @param {number} options.duration - Duration in ms (0 for persistent)
   * @returns {number} Toast ID
   */
  show({ message, type = 'info', duration = 5000 }) {
    this.init();

    const toastId = ++this.toastIdCounter;
    const toast = document.createElement('div');
    toast.className = `tp-toast tp-toast--${type}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'polite');
    
    const content = document.createElement('div');
    content.className = 'tp-toast__content';
    content.textContent = message;
    
    const closeButton = document.createElement('button');
    closeButton.className = 'tp-toast__close';
    closeButton.setAttribute('type', 'button');
    closeButton.setAttribute('aria-label', 'Close notification');
    closeButton.textContent = '×';
    closeButton.addEventListener('click', () => this.hide(toastId));
    
    toast.appendChild(content);
    toast.appendChild(closeButton);
    this.container.appendChild(toast);
    
    this.toasts.set(toastId, toast);
    
    // Auto-hide after duration
    if (duration > 0) {
      setTimeout(() => this.hide(toastId), duration);
    }
    
    return toastId;
  }

  /**
   * Hide a toast notification
   * @param {number} toastId - Toast ID
   */
  hide(toastId) {
    const toast = this.toasts.get(toastId);
    if (toast) {
      toast.classList.add('tp-toast--hiding');
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
        this.toasts.delete(toastId);
      }, 300);
    }
  }

  /**
   * Clear all toasts
   */
  clear() {
    this.toasts.forEach((_, toastId) => this.hide(toastId));
  }
}

/**
 * Banner notification system for persistent issues
 */
class BannerManager {
  constructor() {
    this.banner = null;
  }

  /**
   * Show a banner notification
   * @param {object} options - Banner options
   * @param {string} options.message - Banner message
   * @param {string} options.type - Banner type (info, warning, error)
   * @param {Function} options.onRetry - Retry callback
   */
  show({ message, type = 'info', onRetry = null }) {
    if (typeof document === 'undefined') {
      return;
    }

    this.hide();

    this.banner = document.createElement('div');
    this.banner.className = `tp-banner tp-banner--${type}`;
    this.banner.setAttribute('role', 'alert');
    this.banner.setAttribute('aria-live', 'assertive');
    
    const content = document.createElement('div');
    content.className = 'tp-banner__content';
    content.textContent = message;
    
    const actions = document.createElement('div');
    actions.className = 'tp-banner__actions';
    
    if (onRetry) {
      const retryButton = document.createElement('button');
      retryButton.className = 'tp-banner__button tp-banner__button--primary';
      retryButton.setAttribute('type', 'button');
      retryButton.textContent = 'Retry';
      retryButton.addEventListener('click', onRetry);
      actions.appendChild(retryButton);
    }
    
    const closeButton = document.createElement('button');
    closeButton.className = 'tp-banner__button tp-banner__button--secondary';
    closeButton.setAttribute('type', 'button');
    closeButton.textContent = 'Dismiss';
    closeButton.addEventListener('click', () => this.hide());
    actions.appendChild(closeButton);
    
    this.banner.appendChild(content);
    this.banner.appendChild(actions);
    
    const mainContent = document.querySelector('[data-role="main-content"]');
    if (mainContent) {
      mainContent.insertBefore(this.banner, mainContent.firstChild);
    } else {
      document.body.insertBefore(this.banner, document.body.firstChild);
    }
  }

  /**
   * Hide the banner
   */
  hide() {
    if (this.banner && this.banner.parentNode) {
      this.banner.parentNode.removeChild(this.banner);
      this.banner = null;
    }
  }
}

/**
 * View state manager
 */
class ViewStateManager {
  constructor() {
    this.states = new Map();
    this.cache = new Map();
    this.cacheExpiry = 5 * 60 * 1000; // 5 minutes
  }

  /**
   * Set view state
   * @param {string} route - Route name
   * @param {string} state - State (loading, loaded, error)
   * @param {any} data - Optional data
   */
  setState(route, state, data = null) {
    this.states.set(route, { state, data, timestamp: Date.now() });
  }

  /**
   * Get view state
   * @param {string} route - Route name
   * @returns {object|null}
   */
  getState(route) {
    return this.states.get(route) || null;
  }

  /**
   * Cache data for a route
   * @param {string} route - Route name
   * @param {any} data - Data to cache
   */
  cacheData(route, data) {
    this.cache.set(route, {
      data,
      timestamp: Date.now(),
    });
  }

  /**
   * Get cached data
   * @param {string} route - Route name
   * @returns {any|null}
   */
  getCachedData(route) {
    const cached = this.cache.get(route);
    if (!cached) {
      return null;
    }

    const age = Date.now() - cached.timestamp;
    if (age > this.cacheExpiry) {
      this.cache.delete(route);
      return null;
    }

    return cached.data;
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.cache.clear();
  }
}

/**
 * Progressive enhancement controller
 */
export class ProgressiveEnhancement {
  constructor() {
    this.dataSource = getDataSource();
    this.toastManager = new ToastManager();
    this.bannerManager = new BannerManager();
    this.stateManager = new ViewStateManager();
    this.isEnhanced = false;
    this.streamUnsubscribers = [];
  }

  /**
   * Initialize progressive enhancement
   */
  async init() {
    if (typeof document === 'undefined' || this.isEnhanced) {
      return;
    }

    this.isEnhanced = true;

    // Initialize toast system
    this.toastManager.init();

    // Check if we're in a browser environment with WebSocket support
    if (typeof WebSocket === 'undefined') {
      this.toastManager.show({
        message: 'Real-time updates not available in this environment',
        type: 'warning',
      });
      return;
    }

    // Try to connect to WebSocket for real-time updates
    try {
      await this.dataSource.connectWebSocket();
      this.setupRealtimeStreams();
    } catch (error) {
      console.warn('Failed to connect to WebSocket, will use polling fallback:', error);
    }

    // Setup route change handlers
    this.setupRouteHandlers();

    // Load data for current view
    await this.loadCurrentView();
  }

  /**
   * Setup real-time data streams
   */
  setupRealtimeStreams() {
    // Stream orders
    const ordersUnsubscribe = this.dataSource.streamOrders((data) => {
      this.handleOrderUpdate(data);
    });
    this.streamUnsubscribers.push(ordersUnsubscribe);

    // Stream positions
    const positionsUnsubscribe = this.dataSource.streamPositions((data) => {
      this.handlePositionUpdate(data);
    });
    this.streamUnsubscribers.push(positionsUnsubscribe);

    // Stream PnL
    const pnlUnsubscribe = this.dataSource.streamPnl((data) => {
      this.handlePnlUpdate(data);
    });
    this.streamUnsubscribers.push(pnlUnsubscribe);
  }

  /**
   * Setup route change handlers
   */
  setupRouteHandlers() {
    if (typeof window === 'undefined') {
      return;
    }

    // Listen to hash changes
    window.addEventListener('hashchange', () => {
      this.loadCurrentView();
    });

    // Listen to custom route events
    window.addEventListener('tp:route-change', () => {
      this.loadCurrentView();
    });
  }

  /**
   * Get current route from URL hash
   * @returns {string}
   */
  getCurrentRoute() {
    if (typeof window === 'undefined') {
      return 'overview';
    }

    const hash = window.location.hash.slice(1);
    return hash || 'overview';
  }

  /**
   * Load data for current view
   */
  async loadCurrentView() {
    const route = this.getCurrentRoute();
    
    // Check cache first
    const cachedData = this.stateManager.getCachedData(route);
    if (cachedData) {
      this.updateView(route, cachedData);
      return;
    }

    // Set loading state
    this.stateManager.setState(route, 'loading');
    this.setLoadingState(route, true);

    try {
      const data = await this.fetchDataForRoute(route);
      this.stateManager.setState(route, 'loaded', data);
      this.stateManager.cacheData(route, data);
      this.updateView(route, data);
      this.setLoadingState(route, false);
      this.bannerManager.hide();
    } catch (error) {
      console.error('Failed to load data for route:', route, error);
      this.stateManager.setState(route, 'error', error);
      this.setLoadingState(route, false);
      this.handleLoadError(route, error);
    }
  }

  /**
   * Fetch data for a specific route
   * @param {string} route - Route name
   * @returns {Promise<any>}
   */
  async fetchDataForRoute(route) {
    switch (route) {
      case 'overview':
        return this.dataSource.fetchOverview();
      case 'positions':
        return this.dataSource.fetchPositions();
      case 'orders':
        return this.dataSource.fetchOrders();
      case 'pnl':
        return this.dataSource.fetchPnl();
      case 'signals':
        return this.dataSource.fetchSignals();
      case 'monitoring':
        return this.dataSource.fetchMonitoring();
      case 'community':
        return this.dataSource.fetchCommunity();
      default:
        throw new Error(`Unknown route: ${route}`);
    }
  }

  /**
   * Update view with new data
   * @param {string} route - Route name
   * @param {any} data - View data
   */
  updateView(route, data) {
    // Dispatch custom event with data
    if (typeof window !== 'undefined' && typeof window.CustomEvent === 'function') {
      window.dispatchEvent(
        new CustomEvent('tp:view-update', {
          detail: { route, data },
          bubbles: true,
        })
      );
    }

    // Update view-specific elements
    const viewContainer = document.querySelector(`[data-route="${route}"]`);
    if (viewContainer) {
      // Update data attributes or re-render as needed
      viewContainer.setAttribute('data-loaded', 'true');
    }
  }

  /**
   * Set loading state for a view
   * @param {string} route - Route name
   * @param {boolean} loading - Loading state
   */
  setLoadingState(route, loading) {
    const viewContainer = document.querySelector(`[data-route="${route}"]`);
    if (viewContainer) {
      if (loading) {
        viewContainer.setAttribute('data-loading', 'true');
      } else {
        viewContainer.removeAttribute('data-loading');
      }
    }

    // Update toolbar refresh button
    const refreshButton = document.querySelector('[data-id="refresh"]');
    if (refreshButton) {
      if (loading) {
        refreshButton.setAttribute('disabled', 'disabled');
        refreshButton.setAttribute('aria-busy', 'true');
      } else {
        refreshButton.removeAttribute('disabled');
        refreshButton.removeAttribute('aria-busy');
      }
    }
  }

  /**
   * Handle load error
   * @param {string} route - Route name
   * @param {Error} error - Error object
   */
  handleLoadError(route, error) {
    // Try to use cached data if available
    const cachedData = this.stateManager.getCachedData(route);
    if (cachedData) {
      this.updateView(route, cachedData);
      this.toastManager.show({
        message: 'Using cached data. Network connection issues detected.',
        type: 'warning',
      });
      return;
    }

    // Show banner for persistent errors
    this.bannerManager.show({
      message: `Failed to load ${route} data: ${error.message}`,
      type: 'error',
      onRetry: () => this.loadCurrentView(),
    });
  }

  /**
   * Handle order update from stream
   * @param {any} data - Order data
   */
  handleOrderUpdate(data) {
    if (this.getCurrentRoute() === 'orders') {
      this.updateView('orders', data);
    }
    // Update cached data
    this.stateManager.cacheData('orders', data);
  }

  /**
   * Handle position update from stream
   * @param {any} data - Position data
   */
  handlePositionUpdate(data) {
    if (this.getCurrentRoute() === 'positions') {
      this.updateView('positions', data);
    }
    // Update cached data
    this.stateManager.cacheData('positions', data);
  }

  /**
   * Handle PnL update from stream
   * @param {any} data - PnL data
   */
  handlePnlUpdate(data) {
    if (this.getCurrentRoute() === 'pnl') {
      this.updateView('pnl', data);
    }
    // Update cached data
    this.stateManager.cacheData('pnl', data);
  }

  /**
   * Cleanup resources
   */
  cleanup() {
    // Unsubscribe from all streams
    this.streamUnsubscribers.forEach((unsubscribe) => unsubscribe());
    this.streamUnsubscribers = [];

    // Disconnect data source
    this.dataSource.disconnect();

    // Clear notifications
    this.toastManager.clear();
    this.bannerManager.hide();

    // Clear cache
    this.stateManager.clearCache();

    this.isEnhanced = false;
  }
}

/**
 * Create and initialize progressive enhancement
 * @returns {ProgressiveEnhancement}
 */
export function createProgressiveEnhancement() {
  return new ProgressiveEnhancement();
}

/**
 * Default singleton instance
 */
let defaultInstance = null;

/**
 * Get default progressive enhancement instance
 * @returns {ProgressiveEnhancement}
 */
export function getProgressiveEnhancement() {
  if (!defaultInstance) {
    defaultInstance = createProgressiveEnhancement();
  }
  return defaultInstance;
}

/**
 * Initialize progressive enhancement (convenience function)
 */
export async function initProgressiveEnhancement() {
  const pe = getProgressiveEnhancement();
  await pe.init();
  return pe;
}
