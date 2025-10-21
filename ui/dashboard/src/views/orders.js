import { createLiveTable } from '../components/live_table.js';
import {
  escapeHtml,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatTimestamp,
  serializeForScript,
} from '../core/formatters.js';
import { getMessage, t } from '../i18n/index.js';

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

function getOrdersTableTranslations() {
  const table = getMessage('views.orders.table') || {};
  return {
    columns: table.columns || {},
    badges: table.badges || {},
    empty: table.empty ?? '—',
  };
}

export function renderOrdersView({ orders = [], fills = [], pageSize = 12, page = 1 } = {}) {
  const rows = buildOrderRows(orders, fills);
  const { columns, badges, empty } = getOrdersTableTranslations();
  const sideLabels = (badges.side || {});
  const statusLabels = (badges.status || {});
  const table = createLiveTable({
    columns: [
      {
        id: 'order_id',
        label: columns.order_id || 'Order ID',
        accessor: (row) => row.order_id,
        formatter: (value) => `<code>${escapeHtml(value)}</code>`,
      },
      {
        id: 'symbol',
        label: columns.symbol || 'Symbol',
        accessor: (row) => row.symbol,
        formatter: (value) => `<strong>${escapeHtml(value)}</strong>`,
      },
      {
        id: 'side',
        label: columns.side || 'Side',
        accessor: (row) => row.side,
        formatter: (value) => {
          const key = String(value || '').toLowerCase();
          const label = sideLabels[key] || value;
          const tone = key === 'sell' ? 'negative' : 'positive';
          return `<span class="tp-pill tp-pill--${tone}">${escapeHtml(String(label || value || ''))}</span>`;
        },
      },
      {
        id: 'order_type',
        label: columns.order_type || 'Type',
        accessor: (row) => row.order_type,
        formatter: (value) => escapeHtml(value),
      },
      {
        id: 'quantity',
        label: columns.quantity || 'Quantity',
        accessor: (row) => row.quantity,
        formatter: (value) => escapeHtml(formatNumber(value, { maximumFractionDigits: 4 })),
        sortValue: (row) => row.quantity,
        align: 'right',
      },
      {
        id: 'filledQuantity',
        label: columns.filledQuantity || 'Filled',
        accessor: (row) => row.filledQuantity,
        formatter: (value) => escapeHtml(formatNumber(value, { maximumFractionDigits: 4 })),
        sortValue: (row) => row.filledQuantity,
        align: 'right',
      },
      {
        id: 'remaining',
        label: columns.remaining || 'Remaining',
        accessor: (row) => row.remaining,
        formatter: (value) => escapeHtml(formatNumber(Math.max(value, 0), { maximumFractionDigits: 4 })),
        sortValue: (row) => row.remaining,
        align: 'right',
      },
      {
        id: 'progress',
        label: columns.progress || 'Progress',
        accessor: (row) => row.progress,
        formatter: (value) =>
          `<div class="tp-progress"><span class="tp-progress__bar" style="width:${Math.round(value * 100)}%"></span><span class="tp-progress__label">${escapeHtml(formatPercent(value))}</span></div>`,
        sortValue: (row) => row.progress,
        align: 'right',
      },
      {
        id: 'limitPrice',
        label: columns.limitPrice || 'Limit Price',
        accessor: (row) => row.limitPrice,
        formatter: (value) => (value === null ? escapeHtml(String(empty)) : escapeHtml(formatCurrency(value))),
        sortValue: (row) => row.limitPrice ?? 0,
        align: 'right',
      },
      {
        id: 'avgFillPrice',
        label: columns.avgFillPrice || 'Avg Fill',
        accessor: (row) => row.avgFillPrice,
        formatter: (value) => (value === null ? escapeHtml(String(empty)) : escapeHtml(formatCurrency(value))),
        sortValue: (row) => row.avgFillPrice ?? 0,
        align: 'right',
      },
      {
        id: 'status',
        label: columns.status || 'Status',
        accessor: (row) => row.status,
        formatter: (value) => {
          const label = statusLabels[value] || value;
          return `<span class="tp-status tp-status--${normaliseStatusModifier(value)}">${escapeHtml(String(label || value || ''))}</span>`;
        },
      },
      {
        id: 'lastFill',
        label: columns.lastFill || 'Last Fill',
        accessor: (row) => row.lastFill,
        formatter: (value) => (value ? `<time>${escapeHtml(formatTimestamp(value))}</time>` : escapeHtml(String(empty))),
        sortValue: (row) => row.lastFill,
      },
    ],
    rows,
    sortBy: 'lastFill',
    sortDirection: 'desc',
    pageSize,
  });

  const { html } = table.render(page);
  const totals = rows.reduce(
    (acc, row) => {
      const quantity = Number.isFinite(row.quantity) ? row.quantity : 0;
      const filled = Number.isFinite(row.filledQuantity) ? row.filledQuantity : 0;
      const progress = Number.isFinite(row.progress) ? row.progress : 0;
      acc.grossQuantity += quantity;
      acc.filledQuantity += filled;
      acc.progressTotal += progress;
      return acc;
    },
    { count: rows.length, grossQuantity: 0, filledQuantity: 0, progressTotal: 0 },
  );
  const statusSummary = rows.reduce((acc, row) => {
    const status = row.status || 'UNKNOWN';
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});
  const metadata = serializeForScript({
    route: 'orders',
    totals: {
      count: totals.count,
      grossQuantity: totals.grossQuantity,
      filledQuantity: totals.filledQuantity,
      averageProgress: totals.count ? totals.progressTotal / totals.count : 0,
    },
    statuses: statusSummary,
  });

  return {
    route: 'orders',
    title: t('views.orders.title'),
    html: `
      <section class="tp-view">
        <header class="tp-view__header">
          <h2 class="tp-view__title">${escapeHtml(t('views.orders.heading'))}</h2>
          <p class="tp-view__subtitle">${escapeHtml(t('views.orders.subtitle'))}</p>
        </header>
        ${html}
        <script type="application/json" class="tp-view__meta" data-role="view-meta">${metadata}</script>
      </section>
    `,
    table,
    rows,
  };
}
