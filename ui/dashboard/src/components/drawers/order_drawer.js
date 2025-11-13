/**
 * Order Detail Drawer
 * Interactive drawer with order history, timeline, and actions
 */

import { escapeHtml, formatTimestamp, formatCurrency } from '../../core/formatters.js';

/**
 * @typedef {Object} OrderEvent
 * @property {string} type - Event type (created, filled, cancelled, etc.)
 * @property {string} timestamp - ISO timestamp
 * @property {string} [message] - Event message
 * @property {Object} [details] - Additional event details
 */

/**
 * @typedef {Object} OrderDrawerData
 * @property {string} id - Order ID
 * @property {string} symbol - Trading symbol
 * @property {string} side - Buy/Sell
 * @property {number} quantity - Order quantity
 * @property {number} price - Order price
 * @property {string} status - Order status
 * @property {OrderEvent[]} events - Order events timeline
 * @property {number} [latency] - Order latency in ms
 * @property {Object} [error] - Error details if any
 * @property {Object} [gateway] - Gateway information
 * @property {Object} payload - Full order payload
 */

/**
 * Render order timeline
 * @param {OrderEvent[]} events
 * @returns {string}
 */
function renderTimeline(events = []) {
  if (!events || events.length === 0) {
    return '<p class="tp-drawer__empty">No events recorded.</p>';
  }

  const items = events.map((event) => {
    const typeClass = `tp-timeline__type--${event.type.toLowerCase().replace(/_/g, '-')}`;
    const details = event.details ? `<pre class="tp-timeline__details">${escapeHtml(JSON.stringify(event.details, null, 2))}</pre>` : '';
    
    return `
      <li class="tp-timeline__item ${typeClass}">
        <div class="tp-timeline__marker"></div>
        <div class="tp-timeline__content">
          <div class="tp-timeline__header">
            <span class="tp-timeline__type">${escapeHtml(event.type)}</span>
            <time class="tp-timeline__time" datetime="${escapeHtml(event.timestamp)}">
              ${formatTimestamp(event.timestamp)}
            </time>
          </div>
          ${event.message ? `<p class="tp-timeline__message">${escapeHtml(event.message)}</p>` : ''}
          ${details}
        </div>
      </li>
    `;
  }).join('');

  return `
    <ol class="tp-timeline" role="list" aria-label="Order event timeline">
      ${items}
    </ol>
  `;
}

/**
 * Render order details section
 * @param {OrderDrawerData} order
 * @returns {string}
 */
function renderOrderDetails(order) {
  const priceDisplay = order.price ? formatCurrency(order.price) : '—';
  const quantityDisplay = order.quantity ? String(order.quantity) : '—';
  const statusClass = `tp-drawer__status--${order.status.toLowerCase()}`;
  
  return `
    <div class="tp-drawer__details">
      <div class="tp-drawer__detail-grid">
        <div class="tp-drawer__detail">
          <dt class="tp-drawer__detail-label">Order ID</dt>
          <dd class="tp-drawer__detail-value tp-drawer__detail-value--mono">${escapeHtml(order.id)}</dd>
        </div>
        <div class="tp-drawer__detail">
          <dt class="tp-drawer__detail-label">Status</dt>
          <dd class="tp-drawer__detail-value">
            <span class="tp-drawer__status ${statusClass}">${escapeHtml(order.status)}</span>
          </dd>
        </div>
        <div class="tp-drawer__detail">
          <dt class="tp-drawer__detail-label">Symbol</dt>
          <dd class="tp-drawer__detail-value">${escapeHtml(order.symbol)}</dd>
        </div>
        <div class="tp-drawer__detail">
          <dt class="tp-drawer__detail-label">Side</dt>
          <dd class="tp-drawer__detail-value tp-drawer__detail-value--${order.side.toLowerCase()}">
            ${escapeHtml(order.side)}
          </dd>
        </div>
        <div class="tp-drawer__detail">
          <dt class="tp-drawer__detail-label">Quantity</dt>
          <dd class="tp-drawer__detail-value">${escapeHtml(quantityDisplay)}</dd>
        </div>
        <div class="tp-drawer__detail">
          <dt class="tp-drawer__detail-label">Price</dt>
          <dd class="tp-drawer__detail-value">${escapeHtml(priceDisplay)}</dd>
        </div>
        ${order.latency ? `
          <div class="tp-drawer__detail">
            <dt class="tp-drawer__detail-label">Latency</dt>
            <dd class="tp-drawer__detail-value">${escapeHtml(String(order.latency))} ms</dd>
          </div>
        ` : ''}
        ${order.gateway ? `
          <div class="tp-drawer__detail">
            <dt class="tp-drawer__detail-label">Gateway</dt>
            <dd class="tp-drawer__detail-value">${escapeHtml(order.gateway.name || 'Unknown')}</dd>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

/**
 * Render error section if present
 * @param {Object} [error]
 * @returns {string}
 */
function renderError(error) {
  if (!error) {
    return '';
  }

  return `
    <div class="tp-drawer__error" role="alert">
      <h3 class="tp-drawer__error-title">Error Details</h3>
      <p class="tp-drawer__error-message">${escapeHtml(error.message || 'Unknown error')}</p>
      ${error.code ? `<p class="tp-drawer__error-code">Code: ${escapeHtml(error.code)}</p>` : ''}
      ${error.details ? `<pre class="tp-drawer__error-details">${escapeHtml(JSON.stringify(error.details, null, 2))}</pre>` : ''}
    </div>
  `;
}

/**
 * Render action buttons
 * @param {OrderDrawerData} order
 * @returns {string}
 */
function renderActions(order) {
  const canCancel = ['pending', 'open', 'partial'].includes(order.status.toLowerCase());
  const canRetry = ['failed', 'rejected', 'cancelled'].includes(order.status.toLowerCase());

  if (!canCancel && !canRetry) {
    return '';
  }

  return `
    <div class="tp-drawer__actions">
      ${canRetry ? `
        <button
          type="button"
          class="tp-drawer__action tp-drawer__action--repeat"
          data-action="repeat-order"
          data-order-id="${escapeHtml(order.id)}"
          aria-label="Retry order ${escapeHtml(order.id)}"
        >
          Retry Order
        </button>
      ` : ''}
      ${canCancel ? `
        <button
          type="button"
          class="tp-drawer__action tp-drawer__action--cancel"
          data-action="cancel-order"
          data-order-id="${escapeHtml(order.id)}"
          aria-label="Cancel order ${escapeHtml(order.id)}"
        >
          Cancel Order
        </button>
      ` : ''}
    </div>
  `;
}

/**
 * Render full JSON payload section
 * @param {Object} payload
 * @returns {string}
 */
function renderPayload(payload) {
  return `
    <details class="tp-drawer__payload">
      <summary class="tp-drawer__payload-summary">View Full Payload</summary>
      <pre class="tp-drawer__payload-content">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
    </details>
  `;
}

/**
 * Render order drawer
 * @param {OrderDrawerData} order
 * @returns {string}
 */
export function renderOrderDrawer(order) {
  if (!order || !order.id) {
    return '';
  }

  const timeline = renderTimeline(order.events);
  const details = renderOrderDetails(order);
  const error = renderError(order.error);
  const actions = renderActions(order);
  const payload = renderPayload(order.payload || order);

  return `
    <aside
      class="tp-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
      data-drawer="order-detail"
      data-order-id="${escapeHtml(order.id)}"
    >
      <div class="tp-drawer__overlay" data-action="close-drawer"></div>
      <div class="tp-drawer__panel" tabindex="-1">
        <div class="tp-drawer__header">
          <h2 id="drawer-title" class="tp-drawer__title">
            Order Details
          </h2>
          <button
            type="button"
            class="tp-drawer__close"
            data-action="close-drawer"
            aria-label="Close drawer"
          >
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <div class="tp-drawer__body">
          ${details}
          ${error}
          <section class="tp-drawer__section">
            <h3 class="tp-drawer__section-title">Timeline</h3>
            ${timeline}
          </section>
          ${payload}
        </div>
        ${actions}
      </div>
    </aside>
  `;
}

/**
 * Get drawer enhancement script for client-side behavior
 * @returns {string}
 */
export function getDrawerScript() {
  return `
    <script>
      (function() {
        if (typeof document === 'undefined') return;

        let activeDrawer = null;
        let previousFocus = null;

        function openDrawer(drawer) {
          if (!drawer) return;

          previousFocus = document.activeElement;
          activeDrawer = drawer;
          
          drawer.classList.add('tp-drawer--open');
          drawer.removeAttribute('hidden');
          
          const panel = drawer.querySelector('.tp-drawer__panel');
          if (panel && typeof panel.focus === 'function') {
            panel.focus();
          }

          document.body.style.overflow = 'hidden';
        }

        function closeDrawer(drawer) {
          if (!drawer) return;

          drawer.classList.remove('tp-drawer--open');
          drawer.setAttribute('hidden', '');
          
          document.body.style.overflow = '';
          
          if (previousFocus && typeof previousFocus.focus === 'function') {
            previousFocus.focus();
          }
          
          activeDrawer = null;
          previousFocus = null;
        }

        function trapFocus(event) {
          if (!activeDrawer || event.key !== 'Tab') return;

          const focusable = activeDrawer.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          );
          
          const first = focusable[0];
          const last = focusable[focusable.length - 1];

          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }

        document.addEventListener('click', function(event) {
          const target = event.target;
          
          // Open drawer
          if (target.matches('[data-action="open-drawer"]')) {
            const drawerId = target.getAttribute('data-drawer-target');
            const drawer = drawerId ? document.querySelector(\`[data-drawer="\${drawerId}"]\`) : null;
            if (drawer) {
              openDrawer(drawer);
            }
          }
          
          // Close drawer
          if (target.matches('[data-action="close-drawer"]') || target.closest('[data-action="close-drawer"]')) {
            if (activeDrawer) {
              closeDrawer(activeDrawer);
            }
          }

          // Repeat order
          if (target.matches('[data-action="repeat-order"]')) {
            const orderId = target.getAttribute('data-order-id');
            if (orderId && typeof window.CustomEvent === 'function') {
              window.dispatchEvent(new CustomEvent('tp:order-repeat', { detail: { orderId } }));
            }
          }

          // Cancel order
          if (target.matches('[data-action="cancel-order"]')) {
            const orderId = target.getAttribute('data-order-id');
            if (orderId && typeof window.CustomEvent === 'function') {
              window.dispatchEvent(new CustomEvent('tp:order-cancel', { detail: { orderId } }));
            }
          }
        });

        document.addEventListener('keydown', function(event) {
          if (event.key === 'Escape' && activeDrawer) {
            closeDrawer(activeDrawer);
          }
          trapFocus(event);
        });
      })();
    </script>
  `;
}
