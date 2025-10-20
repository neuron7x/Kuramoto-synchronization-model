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
 * @typedef {import('../types/events').TickEvent} TickEvent
 */

function indexOrders(orders = []) {
  const index = new Map();
  orders.forEach((order) => {
    if (order?.order_id) {
      index.set(order.order_id, order);
    }
  });
  return index;
}

function indexTicks(ticks = []) {
  const index = new Map();
  ticks.forEach((tick) => {
    const mid = Number.isFinite(tick.last_price)
      ? tick.last_price
      : Number.isFinite(tick.bid_price) && Number.isFinite(tick.ask_price)
      ? (tick.bid_price + tick.ask_price) / 2
      : NaN;
    if (Number.isFinite(mid)) {
      index.set(tick.symbol, mid);
    }
  });
  return index;
}

function determineSide(order, fill) {
  const sideFromOrder = order?.side;
  const metadataSide = fill?.metadata?.side;
  const side = sideFromOrder || metadataSide || 'BUY';
  return side.toUpperCase() === 'SELL' ? -1 : 1;
}

function aggregatePositions(fills = [], orders = [], ticks = []) {
  const orderIndex = indexOrders(orders);
  const priceIndex = indexTicks(ticks);
  const aggregates = new Map();

  fills.forEach((fill) => {
    if (!fill || !fill.symbol) {
      return;
    }
    const order = orderIndex.get(fill.order_id);
    const direction = determineSide(order, fill);
    const signedQty = direction * (Number.isFinite(fill.filled_qty) ? fill.filled_qty : 0);
    const fillNotional = (Number.isFinite(fill.fill_price) ? fill.fill_price : 0) * signedQty;
    const entry = aggregates.get(fill.symbol) || {
      symbol: fill.symbol,
      netQuantity: 0,
      netNotional: 0,
      avgPrice: 0,
      marketPrice: priceIndex.get(fill.symbol) ?? NaN,
      exposure: 0,
      pnl: 0,
      lastFill: 0,
      fills: 0,
      totalQuantity: 0,
      totalNotional: 0,
    };
    entry.netQuantity += signedQty;
    entry.netNotional += fillNotional;
    entry.totalQuantity += Math.abs(Number.isFinite(fill.filled_qty) ? fill.filled_qty : 0);
    entry.totalNotional += Math.abs((Number.isFinite(fill.fill_price) ? fill.fill_price : 0) * (Number.isFinite(fill.filled_qty) ? fill.filled_qty : 0));
    entry.lastFill = Math.max(entry.lastFill, Number.isFinite(fill.timestamp) ? fill.timestamp : 0);
    entry.fills += 1;
    const mark = priceIndex.get(fill.symbol);
    if (Number.isFinite(mark)) {
      entry.marketPrice = mark;
    }
    aggregates.set(fill.symbol, entry);
  });

  return Array.from(aggregates.values()).map((entry) => {
    const avgPrice = entry.netQuantity !== 0 ? entry.netNotional / entry.netQuantity : entry.totalQuantity ? entry.totalNotional / entry.totalQuantity : 0;
    const marketPrice = Number.isFinite(entry.marketPrice) ? entry.marketPrice : avgPrice;
    const exposure = Number.isFinite(marketPrice) ? marketPrice * entry.netQuantity : 0;
    const pnl = Number.isFinite(marketPrice) ? (marketPrice - avgPrice) * entry.netQuantity : 0;
    return {
      ...entry,
      avgPrice,
      marketPrice,
      exposure,
      pnl,
    };
  });
}

export function renderPositionsView({
  fills = [],
  orders = [],
  ticks = [],
  pageSize = 10,
  page = 1,
  localization,
} = {}) {
  const rows = aggregatePositions(fills, orders, ticks);
  const table = createLiveTable({
    columns: [
      { id: 'symbol', label: 'Symbol', accessor: (row) => row.symbol, formatter: (value) => `<strong>${escapeHtml(value)}</strong>` },
      {
        id: 'netQuantity',
        label: 'Net Quantity',
        accessor: (row) => row.netQuantity,
        formatter: (value) =>
          `<span>${escapeHtml(formatNumber(value, { maximumFractionDigits: 4 }, localization))}</span>`,
        sortValue: (row) => row.netQuantity,
        align: 'right',
      },
      {
        id: 'avgPrice',
        label: 'Avg Fill Price',
        accessor: (row) => row.avgPrice,
        formatter: (value) => escapeHtml(formatCurrency(value, localization)),
        sortValue: (row) => row.avgPrice,
        align: 'right',
      },
      {
        id: 'marketPrice',
        label: 'Market Price',
        accessor: (row) => row.marketPrice,
        formatter: (value) => escapeHtml(formatCurrency(value, localization)),
        sortValue: (row) => row.marketPrice,
        align: 'right',
      },
      {
        id: 'exposure',
        label: 'Exposure',
        accessor: (row) => row.exposure,
        formatter: (value) => escapeHtml(formatCurrency(value, localization)),
        sortValue: (row) => row.exposure,
        align: 'right',
      },
      {
        id: 'pnl',
        label: 'Unrealised PnL',
        accessor: (row) => row.pnl,
        formatter: (value, row) => {
          const direction = value >= 0 ? 'positive' : 'negative';
          const badge =
            value === 0
              ? ''
              : `<span class="tp-pill tp-pill--${direction}">${escapeHtml(
                  formatPercent(
                    row.marketPrice && row.avgPrice ? (row.marketPrice - row.avgPrice) / (row.avgPrice || 1) : 0,
                    localization,
                  ),
                )}</span>`;
          return `<span>${escapeHtml(formatCurrency(value, localization))}</span>${badge}`;
        },
        sortValue: (row) => row.pnl,
        align: 'right',
      },
      {
        id: 'lastFill',
        label: 'Last Fill',
        accessor: (row) => row.lastFill,
        formatter: (value) => `<time>${escapeHtml(formatTimestamp(value, localization))}</time>`,
        sortValue: (row) => row.lastFill,
      },
    ],
    rows,
    sortBy: 'exposure',
    sortDirection: 'desc',
    pageSize,
  });

  const { html } = table.render(page);

  return {
    route: 'positions',
    title: 'Positions',
    html: `
      <section class="tp-view">
        <header class="tp-view__header">
          <h2 class="tp-view__title">Open Positions</h2>
          <p class="tp-view__subtitle">Aggregated exposures derived from live fill events.</p>
        </header>
        ${html}
      </section>
    `,
    table,
    rows,
  };
}
