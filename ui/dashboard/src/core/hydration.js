/**
 * Client-side hydration utilities
 * Handles mounting and updating dashboard views with live data
 */

/**
 * Generate a hydration script for embedding in HTML
 * @param {object} options - Hydration options
 * @param {boolean} options.enableWebSocket - Enable WebSocket connections
 * @param {string} options.baseUrl - Base API URL
 * @param {string} options.wsUrl - WebSocket URL
 * @param {string} options.modulePath - Path to the dashboard module (default: './src/core/index.js')
 * @returns {string} Hydration script as HTML
 */
export function generateHydrationScript(options = {}) {
  const { enableWebSocket = true, baseUrl = '', wsUrl = '', modulePath = './src/core/index.js' } = options;

  const config = {
    enableWebSocket,
    baseUrl: baseUrl || undefined,
    wsUrl: wsUrl || undefined,
  };

  const configJson = JSON.stringify(config, null, 2);
  // Properly escape backslashes first, then single quotes to prevent injection
  const modulePathEscaped = modulePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

  return `
    <script type="module">
      // Client-side hydration configuration
      const hydrationConfig = ${configJson};
      
      // Store config globally for progressive enhancement
      if (!window.tp) {
        window.tp = {};
      }
      window.tp.hydrationConfig = hydrationConfig;

      // Import and initialize progressive enhancement
      import { initProgressiveEnhancement, createDataSource } from '${modulePathEscaped}';
      
      async function hydrateViews() {
        try {
          // Create data source with custom config if provided
          const dataSourceOptions = {};
          if (hydrationConfig.baseUrl) {
            dataSourceOptions.baseUrl = hydrationConfig.baseUrl;
          }
          if (hydrationConfig.wsUrl) {
            dataSourceOptions.wsUrl = hydrationConfig.wsUrl;
          }
          
          // Initialize progressive enhancement
          await initProgressiveEnhancement();
          
          console.info('[TradePulse] Dashboard hydrated successfully');
        } catch (error) {
          console.error('[TradePulse] Hydration failed:', error);
        }
      }

      // Start hydration when DOM is ready
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', hydrateViews);
      } else {
        hydrateViews();
      }
    </script>
  `;
}

/**
 * Attach a view update handler to the DOM
 * This allows views to be updated dynamically when data arrives
 * @param {string} route - Route name
 * @param {Function} updateCallback - Callback function to handle updates
 */
export function attachViewUpdateHandler(route, updateCallback) {
  if (typeof window === 'undefined') {
    return () => {}; // No-op in SSR
  }

  const handler = (event) => {
    if (event.detail && event.detail.route === route) {
      updateCallback(event.detail.data);
    }
  };

  window.addEventListener('tp:view-update', handler);

  // Return cleanup function
  return () => {
    window.removeEventListener('tp:view-update', handler);
  };
}

/**
 * Mark an element as a hydration target
 * @param {string} route - Route name
 * @param {HTMLElement} element - DOM element
 */
export function markHydrationTarget(route, element) {
  if (!element) {
    return;
  }
  
  element.setAttribute('data-hydration-target', route);
  element.setAttribute('data-hydration-state', 'pending');
}

/**
 * Update hydration state
 * @param {HTMLElement} element - DOM element
 * @param {string} state - New state (pending, loading, loaded, error)
 */
export function updateHydrationState(element, state) {
  if (!element) {
    return;
  }
  
  element.setAttribute('data-hydration-state', state);
}

/**
 * Create a loading placeholder
 * @param {string} message - Loading message
 * @returns {string} HTML string
 */
export function createLoadingPlaceholder(message = 'Loading...') {
  return `
    <div class="tp-loading-placeholder" role="status" aria-live="polite">
      <div class="tp-loading-placeholder__spinner"></div>
      <p class="tp-loading-placeholder__message">${message}</p>
    </div>
  `;
}

/**
 * Create an error placeholder
 * @param {string} message - Error message
 * @param {Function} onRetry - Retry callback
 * @returns {string} HTML string
 */
export function createErrorPlaceholder(message = 'Failed to load data', onRetry = null) {
  const retryButton = onRetry
    ? `<button type="button" class="tp-error-placeholder__retry" onclick="this.dispatchEvent(new CustomEvent('tp:retry', { bubbles: true }))">Retry</button>`
    : '';
  
  return `
    <div class="tp-error-placeholder" role="alert">
      <p class="tp-error-placeholder__message">${message}</p>
      ${retryButton}
    </div>
  `;
}

/**
 * Styles for hydration placeholders
 */
export const HYDRATION_STYLES = `
  .tp-loading-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 1.5rem;
    gap: 1rem;
  }

  .tp-loading-placeholder__spinner {
    width: 2.5rem;
    height: 2.5rem;
    border: 3px solid rgba(6, 182, 212, 0.2);
    border-top-color: #06b6d4;
    border-radius: 50%;
    animation: tp-spinner-rotate 0.8s linear infinite;
  }

  @keyframes tp-spinner-rotate {
    to {
      transform: rotate(360deg);
    }
  }

  .tp-loading-placeholder__message {
    font-size: 0.875rem;
    color: rgba(240, 249, 255, 0.7);
    margin: 0;
  }

  .tp-error-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 1.5rem;
    gap: 1rem;
    text-align: center;
  }

  .tp-error-placeholder__message {
    font-size: 0.875rem;
    color: rgba(239, 68, 68, 0.9);
    margin: 0;
  }

  .tp-error-placeholder__retry {
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #ffffff;
    background: #06b6d4;
    border: 1px solid #06b6d4;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .tp-error-placeholder__retry:hover {
    background: #0891b2;
    border-color: #0891b2;
  }

  .tp-error-placeholder__retry:focus {
    outline: 2px solid #06b6d4;
    outline-offset: 2px;
  }

  [data-hydration-state="pending"] {
    min-height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  [data-hydration-state="loading"] {
    opacity: 0.6;
    pointer-events: none;
  }

  [data-hydration-state="error"] {
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 8px;
  }
`;
