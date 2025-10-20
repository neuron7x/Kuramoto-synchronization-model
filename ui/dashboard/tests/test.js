import assert from 'assert';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import {
  createStrategyConfigurator,
  compareBacktests,
  exportReport,
  DashboardState,
  renderDashboard,
  DASHBOARD_STYLES,
  formatCurrency,
  formatPercent,
  createRouter,
} from '../src/core/index.js';
import {
  TRACEPARENT_HEADER,
  createTraceparent,
  ensureTraceHeaders,
  extractTraceparent,
  subscribeTelemetry,
} from '../src/core/telemetry.js';
import { renderPositionsView } from '../src/views/positions.js';
import { renderOrdersView } from '../src/views/orders.js';
import { renderPnlQuotesView } from '../src/views/pnl_quotes.js';
import { renderAreaChart } from '../src/components/area_chart.js';
import { createLiveTable, LiveTable } from '../src/components/live_table.js';
import {
  escapeHtml,
  formatNumber,
  formatTimestamp,
  formatCurrency as formatCurrencyLocalized,
  formatPercent as formatPercentLocalized,
} from '../src/core/formatters.js';
import {
  getLocalizationContext,
  registerLocaleCatalog,
  resetLocalizationForTests,
} from '../src/i18n/number_format.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CATALOG_PATH = path.resolve(__dirname, '../../..', 'configs', 'localization', 'locales.yaml');

resetLocalizationForTests();
registerLocaleCatalog(JSON.parse(fs.readFileSync(CATALOG_PATH, 'utf-8')));

// --- Core strategy + reporting utilities ------------------------------------------------------

const configurator = createStrategyConfigurator([
  { name: 'trend', defaults: { lookback: 20, threshold: 0.6 } },
  { name: 'mean_revert', defaults: { lookback: 10, zScore: 1.5 } },
]);

const updated = configurator.update('trend', { threshold: 0.8 });
assert.strictEqual(updated.threshold, 0.8, 'update should override fields');
assert.deepStrictEqual(configurator.get('trend'), updated, 'config should persist updates');
assert.strictEqual(configurator.list().length, 2, 'list should expose all strategies');

const backtests = [
  {
    metadata: { id: 'bt-1', strategy: 'trend' },
    metrics: { sharpe: 1.5, pnl: 1200 },
  },
  {
    metadata: { id: 'bt-2', strategy: 'mean_revert' },
    metrics: { sharpe: 0.9, pnl: 800 },
  },
];

const comparison = compareBacktests(backtests);
assert.strictEqual(comparison.metric, 'sharpe');
assert.strictEqual(comparison.leaders.best.strategy, 'trend');
assert.ok(comparison.spread.delta > 0, 'spread delta should be positive');

const jsonReport = exportReport(comparison, { format: 'json' });
const parsed = JSON.parse(jsonReport);
assert.strictEqual(parsed.metric, 'sharpe');
assert.strictEqual(parsed.leaders.best.strategy, 'trend');

const csvReport = exportReport(comparison, { format: 'csv', precision: 2 });
assert.ok(csvReport.includes('trend'));
assert.ok(csvReport.includes('1.50'));

const injectionSummary = {
  ranking: [
    {
      id: '=HYPERLINK("http://example.com","click")',
      strategy: '=trend|bold*',
      score: 2.5,
    },
  ],
};
const protectedCsv = exportReport(injectionSummary, { format: 'csv', precision: 1 });
assert.ok(
  protectedCsv.includes("'=HYPERLINK\\("),
  'CSV export should neutralise formula injection attempts by prefixing risky values',
);
assert.ok(
  protectedCsv.includes("'=trend\\|bold\\*"),
  'CSV export should escape Markdown meta characters',
);

const protectedMarkdown = exportReport(injectionSummary, {
  format: 'markdown',
  precision: 1,
});
assert.ok(
  protectedMarkdown.includes("'=trend\\|bold\\*"),
  'Markdown export should escape Markdown meta characters while keeping content readable',
);
assert.ok(
  protectedMarkdown.includes('2.5'),
  'Markdown export should include neutralised numeric score',
);

const state = new DashboardState({ strategies: configurator.list(), backtests });
state.updateStrategy('mean_revert', { zScore: 2.0 });
state.addBacktest({ metadata: { id: 'bt-3', strategy: 'volatility' }, metrics: { sharpe: 2.1 } });
const exportedMarkdown = state.export('markdown');
assert.ok(exportedMarkdown.includes('volatility'));

assert.strictEqual(escapeHtml('<script>'), '&lt;script&gt;');
const defaultLocalization = getLocalizationContext();
assert.strictEqual(formatNumber(1250.567, { maximumFractionDigits: 1 }, defaultLocalization), '1,250.6');
assert.strictEqual(formatTimestamp(0, defaultLocalization), '12/31/1969, 19:00:00 EST');

const germanLocalization = getLocalizationContext({ locale: 'de-DE' });
assert.strictEqual(
  formatNumber(1234567.89, { maximumFractionDigits: 2 }, germanLocalization),
  '1.234.567,89',
);
assert.strictEqual(formatPercentLocalized(0.1234, germanLocalization), '12,34 %');

const ukrainianLocalization = getLocalizationContext({ locale: 'uk-UA' });
assert.strictEqual(
  formatNumber(1234.56, { maximumFractionDigits: 2 }, ukrainianLocalization),
  '1 234,56',
);
assert.strictEqual(formatPercentLocalized(0.075, ukrainianLocalization), '7,50%');

const japaneseLocalization = getLocalizationContext({ locale: 'ja-JP' });
assert.strictEqual(formatCurrencyLocalized(1234.56, undefined, japaneseLocalization), '￥1,235');
assert.strictEqual(formatTimestamp(0, japaneseLocalization), '1970/01/01 09:00:00 JST');

const telemetryEvents = [];
const unsubscribeTelemetry = subscribeTelemetry((entry) => telemetryEvents.push(entry));
getLocalizationContext({ preferredLocales: ['zz-ZZ'] });
unsubscribeTelemetry();
assert.ok(telemetryEvents.some((event) => event.event === 'localization.fallback'));

console.log('core reporting tests passed');

// --- Telemetry helpers -----------------------------------------------------------------------

const generatedTraceparent = createTraceparent();
assert.ok(generatedTraceparent.startsWith('00-'));
const headers = ensureTraceHeaders({}, generatedTraceparent).headers;
assert.strictEqual(headers[TRACEPARENT_HEADER], generatedTraceparent);
assert.strictEqual(extractTraceparent(headers), generatedTraceparent);
console.log('telemetry tests passed');

const now = Date.now();
const orderEvents = [
  {
    event_id: 'order-1',
    schema_version: '1',
    symbol: 'AAPL',
    timestamp: now - 120000,
    order_id: 'ord-1',
    side: 'BUY',
    order_type: 'LIMIT',
    quantity: 100,
    price: 150.25,
    time_in_force: 'DAY',
    routing: 'XNAS',
    metadata: {},
  },
  {
    event_id: 'order-2',
    schema_version: '1',
    symbol: 'MSFT',
    timestamp: now - 90000,
    order_id: 'ord-2',
    side: 'SELL',
    order_type: 'LIMIT',
    quantity: 50,
    price: 311.4,
    time_in_force: 'DAY',
    routing: 'XNAS',
    metadata: {},
  },
];

const fillEvents = [
  {
    event_id: 'fill-1',
    schema_version: '1',
    symbol: 'AAPL',
    timestamp: now - 60000,
    order_id: 'ord-1',
    fill_id: 'fill-1',
    status: 'PARTIAL',
    filled_qty: 60,
    fill_price: 149.9,
    fees: 1.2,
    liquidity: 'MAKER',
    metadata: {},
  },
  {
    event_id: 'fill-2',
    schema_version: '1',
    symbol: 'AAPL',
    timestamp: now - 30000,
    order_id: 'ord-1',
    fill_id: 'fill-2',
    status: 'FILLED',
    filled_qty: 40,
    fill_price: 150.75,
    metadata: {},
  },
  {
    event_id: 'fill-3',
    schema_version: '1',
    symbol: 'MSFT',
    timestamp: now - 15000,
    order_id: 'ord-2',
    fill_id: 'fill-3',
    status: 'FILLED',
    filled_qty: 50,
    fill_price: 310.95,
    metadata: {},
  },
];

const ticks = [
  {
    event_id: 'tick-1',
    schema_version: '1',
    symbol: 'AAPL',
    timestamp: now - 5000,
    bid_price: 151.1,
    ask_price: 151.3,
    last_price: 151.2,
  },
  {
    event_id: 'tick-2',
    schema_version: '1',
    symbol: 'MSFT',
    timestamp: now - 4000,
    bid_price: 310.5,
    ask_price: 310.7,
    last_price: 310.6,
  },
];

const pnlPoints = [
  { timestamp: now - 3600000, value: 12500 },
  { timestamp: now - 1800000, value: 16850 },
  { timestamp: now - 600000, value: 17200 },
  { timestamp: now - 300000, value: 18120 },
  { timestamp: now, value: 18750 },
];

const quotes = ticks.map((tick) => ({
  event_id: `quote-${tick.symbol}`,
  schema_version: '1',
  symbol: tick.symbol,
  timestamp: tick.timestamp,
  bid_price: tick.bid_price,
  ask_price: tick.ask_price,
  last_price: tick.last_price,
}));

// --- Live table component -------------------------------------------------------------------

const table = createLiveTable({
  columns: [
    { id: 'symbol', label: 'Symbol' },
    { id: 'pnl', label: 'PnL', sortValue: (row) => row.pnl, formatter: (value) => `<strong>${escapeHtml(value)}</strong>`, align: 'right' },
  ],
  rows: [
    { symbol: 'XYZ', pnl: 10 },
    { symbol: 'ABC', pnl: 20 },
  ],
  sortBy: 'pnl',
  sortDirection: 'asc',
  pageSize: 1,
});

assert.ok(table instanceof LiveTable, 'createLiveTable should return a LiveTable instance');

const ascRows = table.getSortedRows();
assert.deepStrictEqual(ascRows.map((row) => row.symbol), ['XYZ', 'ABC']);

table.setSort('pnl', 'desc');
const descRows = table.getSortedRows();
assert.deepStrictEqual(descRows.map((row) => row.symbol), ['ABC', 'XYZ']);

const { page, pageCount, html: tableHtml } = table.render(10);
assert.strictEqual(page, 2, 'page should clamp to the last available page');
assert.strictEqual(pageCount, 2);
assert.ok(tableHtml.includes('<table'), 'render should output a table element');

table.setPageSize(2);
table.setRows([{ symbol: 'AAA', pnl: 5 }]);
const emptyTable = table.render();
assert.strictEqual(emptyTable.totalRows, 1);
assert.ok(!emptyTable.html.includes('No data available'), 'table renders populated rows when present');

assert.throws(() => new LiveTable({ columns: [] }), /at least one column/);
assert.throws(() => table.setPageSize(0), /positive number/);

console.log('live table tests passed');

// --- Area chart component -------------------------------------------------------------------

const areaChart = renderAreaChart({
  id: 'test',
  width: 100,
  height: 50,
  series: [
    { timestamp: 1, value: 100 },
    { timestamp: 2, value: 100 },
  ],
});
assert.ok(areaChart.html.includes('tp-area-chart'));
assert.strictEqual(areaChart.min, 99, 'identical values should expand range symmetrically');
assert.strictEqual(areaChart.max, 101);

const emptyChart = renderAreaChart({ series: [{ timestamp: 3, value: NaN }] });
assert.strictEqual(emptyChart.points.length, 0, 'non-finite values should be filtered out');
assert.ok(emptyChart.html.includes('Chart data is not available'), 'empty charts should display placeholder');

console.log('area chart tests passed');

// --- Dashboard shell + views ----------------------------------------------------------------

const dashboardView = renderDashboard({
  route: 'positions',
  header: {
    title: 'Execution Control Center',
    subtitle: 'Live oversight across strategies.',
    tags: ['derivatives', 'equities'],
  },
  positions: { fills: fillEvents, orders: orderEvents, ticks },
  orders: { orders: orderEvents, fills: fillEvents },
  pnl: { pnlPoints, quotes },
});

assert.ok(dashboardView.html.includes('PnL &amp; Quotes'), 'navigation should expose pnl route');
assert.ok(dashboardView.html.includes('Open Positions'), 'positions component should be rendered for active route');
assert.ok(dashboardView.styles.includes('.tp-live-table'), 'styles should include live table classes');
assert.strictEqual(dashboardView.styles, DASHBOARD_STYLES, 'render should expose shared stylesheet reference');
assert.strictEqual(dashboardView.route, 'positions');

const navigationLinks = (dashboardView.html.match(/<a class=\"tp-nav__link/g) || []).length;
assert.strictEqual(navigationLinks, 3, 'dashboard should render all navigation links');

const applePosition = dashboardView.view.rows.find((row) => row.symbol === 'AAPL');
assert.ok(applePosition, 'positions view should aggregate AAPL position');
assert.strictEqual(Math.round(applePosition.netQuantity), 100);
assert.ok(applePosition.exposure > 0, 'exposure should be positive for long positions');

const ordersView = renderOrdersView({ orders: orderEvents, fills: fillEvents });
assert.ok(ordersView.html.includes('Order Blotter'));
const orderProgress = ordersView.table.getSortedRows()[0];
assert.ok(orderProgress.progress <= 1, 'order progress must be clamped');
assert.ok(orderProgress.remaining >= 0, 'remaining quantity should never be negative');

const pnlView = renderPnlQuotesView({ pnlPoints, quotes });
assert.ok(pnlView.html.includes('Net PnL'));
assert.ok(pnlView.charts.pnl.points.length > 0);
assert.ok(pnlView.charts.quotes.points.every((point, index, arr) => index === 0 || arr[index - 1].timestamp <= point.timestamp));

const router = createRouter({
  defaultRoute: 'orders',
  routes: {
    orders: () => renderOrdersView({ orders: orderEvents, fills: fillEvents }),
    pnl: () => pnlView,
  },
});
const active = router.navigate('pnl');
assert.strictEqual(active.name, 'pnl');
assert.ok(active.view.html.includes('PnL & Quotes Intelligence'));
assert.deepStrictEqual(router.list().sort(), ['orders', 'pnl']);
assert.throws(() => router.register('invalid route', () => null), /Invalid route name/);
assert.throws(() => router.register('bad', 123), /must be a function/);
assert.throws(() => router.navigate('missing'), /Unknown route/);
assert.strictEqual(router.navigate(null).name, 'orders', 'null navigation should fallback to default route');

assert.strictEqual(formatCurrency(10500), '$10,500');
assert.strictEqual(formatPercent(0.256), '25.60%');
assert.strictEqual(formatPercent(0.025), '2.50%');
console.log('dashboard ui rendering tests passed');

const sanitizedView = renderPositionsView({
  fills: [
    {
      event_id: 'fill-sanitized',
      schema_version: '1',
      symbol: '<b>Automation</b>',
      timestamp: now,
      order_id: 'ord-x',
      fill_id: 'fill-x',
      status: 'FILLED',
      filled_qty: 10,
      fill_price: 100,
      metadata: { side: 'BUY' },
    },
  ],
  orders: [],
  ticks: [],
});

assert.ok(!sanitizedView.html.includes('<script>'), 'positions view should escape script tags');
assert.ok(sanitizedView.html.includes('&lt;b&gt;Automation&lt;/b&gt;'), 'escaped HTML should remain visible as text');

const pnlStats = renderPnlQuotesView({ pnlPoints: [], quotes: [] });
assert.ok(pnlStats.html.includes('Chart data is not available'), 'empty series should surface chart placeholder');

console.log('view sanitisation tests passed');
