import { createLiveTable } from '../components/live_table.js';
import {
  escapeHtml,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatTimestamp,
} from '../core/formatters.js';

/**
 * @typedef {import('../types/events').OrderEvent} OrderEvent
 * @typedef {import('../types/events').FillEvent} FillEvent
 */

function aggregateFills(fills = []) {
  const map = new Map();
  fills.forEach((fill) => {
    if (!fill?.order_id) {
      return;
    }
    const entry = map.get(fill.order_id) || {
      filledQuantity: 0,
      notional: 0,
      lastStatus: fill.status || null,
      lastFill: 0,
    };
    const qty = Number.isFinite(fill.filled_qty) ? fill.filled_qty : 0;
    const price = Number.isFinite(fill.fill_price) ? fill.fill_price : 0;
    entry.filledQuantity += qty;
    entry.notional += qty * price;
    entry.lastStatus = fill.status || entry.lastStatus;
    entry.lastFill = Math.max(entry.lastFill, Number.isFinite(fill.timestamp) ? fill.timestamp : 0);
    map.set(fill.order_id, entry);
  });
  return map;
}

function normaliseStatusModifier(value) {
  if (value == null) {
    return 'unknown';
  }
  const slug = String(value)
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9_-]+/g, '-');
  return slug || 'unknown';
}

function buildOrderRows(orders = [], fills = []) {
  const fillIndex = aggregateFills(fills);
  return orders.map((order) => {
    const fill = fillIndex.get(order.order_id) || {
      filledQuantity: 0,
      notional: 0,
      lastStatus: null,
      lastFill: 0,
    };
    const quantity = Number.isFinite(order.quantity) ? order.quantity : 0;
    const limitPrice = Number.isFinite(order.price) ? order.price : null;
    const progress = quantity > 0 ? Math.min(fill.filledQuantity / quantity, 1) : fill.filledQuantity > 0 ? 1 : 0;
    const remaining = quantity - fill.filledQuantity;
    const avgFillPrice = fill.filledQuantity > 0 ? fill.notional / fill.filledQuantity : null;
    const status = fill.lastStatus || (progress >= 1 ? 'FILLED' : 'WORKING');

    return {
      ...order,
      quantity,
      limitPrice,
      progress,
      remaining,
      avgFillPrice,
      status,
      lastFill: fill.lastFill,
      filledQuantity: fill.filledQuantity,
    };
  });
}

export function renderOrdersView({
  orders = [],
  fills = [],
  pageSize = 12,
  page = 1,
  localization,
} = {}) {
  const rows = buildOrderRows(orders, fills);
  const table = createLiveTable({
    columns: [
      { id: 'order_id', label: 'Order ID', accessor: (row) => row.order_id, formatter: (value) => `<code>${escapeHtml(value)}</code>` },
      { id: 'symbol', label: 'Symbol', accessor: (row) => row.symbol, formatter: (value) => `<strong>${escapeHtml(value)}</strong>` },
      {
        id: 'side',
        label: 'Side',
        accessor: (row) => row.side,
        formatter: (value) => `<span class="tp-pill tp-pill--${String(value).toLowerCase() === 'sell' ? 'negative' : 'positive'}">${escapeHtml(value)}</span>`,
      },
      {
        id: 'order_type',
        label: 'Type',
        accessor: (row) => row.order_type,
        formatter: (value) => escapeHtml(value),
      },
      {
        id: 'quantity',
        label: 'Quantity',
        accessor: (row) => row.quantity,
        formatter: (value) => escapeHtml(formatNumber(value, { maximumFractionDigits: 4 }, localization)),
        sortValue: (row) => row.quantity,
        align: 'right',
      },
      {
        id: 'filledQuantity',
        label: 'Filled',
        accessor: (row) => row.filledQuantity,
        formatter: (value) => escapeHtml(formatNumber(value, { maximumFractionDigits: 4 }, localization)),
        sortValue: (row) => row.filledQuantity,
        align: 'right',
      },
      {
        id: 'remaining',
        label: 'Remaining',
        accessor: (row) => row.remaining,
        formatter: (value) =>
          escapeHtml(formatNumber(Math.max(value, 0), { maximumFractionDigits: 4 }, localization)),
        sortValue: (row) => row.remaining,
        align: 'right',
      },
      {
        id: 'progress',
        label: 'Progress',
        accessor: (row) => row.progress,
        formatter: (value) =>
          `<div class="tp-progress"><span class="tp-progress__bar" style="width:${Math.round(value * 100)}%"></span><span class="tp-progress__label">${escapeHtml(formatPercent(value, localization))}</span></div>`,
        sortValue: (row) => row.progress,
        align: 'right',
      },
      {
        id: 'limitPrice',
        label: 'Limit Price',
        accessor: (row) => row.limitPrice,
        formatter: (value) => (value === null ? '—' : escapeHtml(formatCurrency(value, localization))),
        sortValue: (row) => row.limitPrice ?? 0,
        align: 'right',
      },
      {
        id: 'avgFillPrice',
        label: 'Avg Fill',
        accessor: (row) => row.avgFillPrice,
        formatter: (value) => (value === null ? '—' : escapeHtml(formatCurrency(value, localization))),
        sortValue: (row) => row.avgFillPrice ?? 0,
        align: 'right',
      },
      {
        id: 'status',
        label: 'Status',
        accessor: (row) => row.status,
        formatter: (value) => `<span class="tp-status tp-status--${normaliseStatusModifier(value)}">${escapeHtml(value)}</span>`,
      },
      {
        id: 'lastFill',
        label: 'Last Fill',
        accessor: (row) => row.lastFill,
        formatter: (value) =>
          value ? `<time>${escapeHtml(formatTimestamp(value, localization))}</time>` : '—',
        sortValue: (row) => row.lastFill,
      },
    ],
    rows,
    sortBy: 'lastFill',
    sortDirection: 'desc',
    pageSize,
  });

  const { html } = table.render(page);

  return {
    route: 'orders',
    title: 'Orders',
    html: `
      <section class="tp-view">
        <header class="tp-view__header">
          <h2 class="tp-view__title">Order Blotter</h2>
          <p class="tp-view__subtitle">Live order flow enriched with fill progress and execution telemetry.</p>
        </header>
        ${html}
      </section>
    `,
    table,
    rows,
  };
}
