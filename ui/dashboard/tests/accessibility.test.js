import assert from 'assert';

const TEST_LEVEL = 'L7';
console.info(`[${TEST_LEVEL}] ui/dashboard accessibility contract check`);

import { renderDashboard } from '../src/core/index.js';
import { renderOrdersView } from '../src/views/orders.js';
import { renderPositionsView } from '../src/views/positions.js';
import { renderAreaChart } from '../src/components/area_chart.js';

const baseTimestamp = 1700000000000;

const orders = {
  orders: [
    {
      event_id: 'order-a11y-1',
      schema_version: '1',
      symbol: 'AAPL',
      timestamp: baseTimestamp,
      order_id: 'ord-a11y',
      status: 'WORKING',
      side: 'BUY',
      quantity: 10,
      filled_quantity: 0,
    },
  ],
  fills: [],
};

const positions = {
  fills: [
    {
      event_id: 'fill-a11y-1',
      schema_version: '1',
      symbol: 'AAPL',
      timestamp: baseTimestamp,
      order_id: 'ord-a11y',
      fill_id: 'fill-a11y',
      status: 'FILLED',
      filled_qty: 10,
      fill_price: 150,
      metadata: { side: 'BUY' },
    },
  ],
  orders: orders.orders,
  ticks: [
    { symbol: 'AAPL', last_price: 151, timestamp: baseTimestamp },
  ],
};

const pnl = {
  pnlPoints: [
    { timestamp: baseTimestamp, value: 1000 },
    { timestamp: baseTimestamp + 60_000, value: 1010 },
  ],
  quotes: [
    { timestamp: baseTimestamp, mid: 150 },
    { timestamp: baseTimestamp + 60_000, mid: 151 },
  ],
};

const signals = {
  signals: [
    { id: 'sig-a', label: 'Buy', strength: 0.7, ttl_seconds: 300, created_at: baseTimestamp },
    { id: 'sig-b', label: 'Reduce', strength: -0.2, ttl_seconds: 0, created_at: baseTimestamp - 600_000 },
  ],
};

const dashboard = renderDashboard({
  route: 'orders',
  orders,
  positions,
  pnl,
  signals,
  header: { title: 'Accessibility Dashboard', subtitle: 'Ensuring inclusive UX.' },
});

assert.ok(dashboard.html.includes('aria-label="Primary"'), 'navigation should expose primary aria label');
assert.ok(dashboard.html.includes('aria-current="page"'), 'active navigation link should set aria-current');

const ordersView = renderOrdersView(orders);
assert.ok(ordersView.html.includes('role="table"'), 'orders table should use table role for screen readers');
assert.ok(
  ordersView.html.includes('aria-describedby="tp-live-table-summary-'),
  'summary should annotate table context with descriptive id',
);

const positionsView = renderPositionsView(positions);
assert.ok(positionsView.table.render().html.includes('role="table"'), 'positions table render should expose table role');

const areaChart = renderAreaChart({
  id: 'a11y-chart',
  width: 400,
  height: 200,
  series: pnl.pnlPoints,
});
assert.ok(areaChart.html.includes('role="img"'), 'charts should include img role for narration');
assert.ok(areaChart.html.includes('aria-label'), 'charts should declare accessible label');
