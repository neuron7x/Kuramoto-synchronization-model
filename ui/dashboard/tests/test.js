import assert from 'assert';
import './accessibility.test.js';

const TEST_LEVEL = 'L7';
console.info(`[${TEST_LEVEL}] ui/dashboard functional regression suite`);
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
  renderOverviewView,
  renderCommunityView,
} from '../src/core/index.js';
import {
  TRACEPARENT_HEADER,
  createTraceparent,
  ensureTraceHeaders,
  extractTraceparent,
} from '../src/core/telemetry.js';
import { renderPositionsView } from '../src/views/positions.js';
import { renderOrdersView } from '../src/views/orders.js';
import { renderPnlQuotesView } from '../src/views/pnl_quotes.js';
import { renderSignalsView } from '../src/views/signals.js';
import { renderMonitoringView } from '../src/views/monitoring.js';
import { renderAreaChart } from '../src/components/area_chart.js';
import { createLiveTable, LiveTable } from '../src/components/live_table.js';
import { escapeHtml, formatNumber, formatTimestamp } from '../src/core/formatters.js';
import { supportedLocales } from '../src/i18n/config.js';

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
assert.strictEqual(formatNumber(1250.567, { maximumFractionDigits: 1 }), '1,250.6');
assert.strictEqual(formatTimestamp(0), '1970-01-01 00:00:00.000 UTC');
assert.ok(
  ['it-IT', 'hi-IN', 'pl-PL', 'ar-SA'].every((code) => supportedLocales.includes(code)),
  'supported locales should include newly added language packs',
);
assert.ok(supportedLocales.length >= 12, 'supported locales should list expanded catalogue');

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

const communityProfile = {
  metrics: {
    maintainers: 14,
    sponsors: 22,
    sponsorshipMonthly: 6400,
    monthlyDownloads: 185000,
    responseHours: 5.2,
    goodFirstIssues: 26,
    mentorshipSeats: 12,
  },
  engagement: [
    {
      period: '2025-01',
      contributions: 320,
      newcomers: 28,
      releases: 2,
      highlights: ['Playbook v2 shortened onboarding to 4 days.'],
    },
    {
      period: '2025-02',
      contributions: 344,
      newcomers: 32,
      releases: 3,
      highlights: ['Regional hubs launched async review shifts.'],
    },
  ],
  programs: [
    {
      name: 'Mentorship sprint',
      description: 'Six-week track pairing maintainers with first-time contributors.',
      url: 'https://geosync.dev/community/mentorship',
    },
    {
      name: 'Observability guild',
      description: 'Weekly office hours focused on instrumentation and tracing contributions.',
      url: 'https://geosync.dev/community/observability-guild',
    },
  ],
  events: [
    {
      name: 'Community call Q1',
      date: '2025-02-12T16:00:00Z',
      type: 'Virtual',
      location: 'Online',
      url: 'https://geosync.dev/events/community-call',
    },
    {
      name: 'Contributor summit',
      date: '2025-04-18T09:00:00Z',
      type: 'Hybrid',
      location: 'Barcelona / Remote',
      url: 'https://geosync.dev/events/summit',
    },
  ],
  resources: [
    {
      label: 'Contribution playbook',
      description: 'Step-by-step onboarding with tooling, workflows, and review expectations.',
      url: 'https://geosync.dev/docs/contribute',
      category: 'Guides',
    },
    {
      label: 'Design system',
      description: 'Reusable tokens, components, and accessibility guidance.',
      url: 'https://geosync.dev/design-system',
      category: 'Design',
    },
    {
      label: 'Incident response runbook',
      description: 'Checklist for coordinating responders and status updates.',
      url: 'https://geosync.dev/ops/incident',
      category: 'Operations',
    },
  ],
  hubs: [
    {
      region: 'North America',
      leads: 6,
      focus: 'Quant research enablement and governance.',
      location: 'Remote / NYC',
      url: 'https://geosync.dev/community/hubs/na',
    },
    {
      region: 'EMEA',
      leads: 4,
      focus: 'Localization reviews and regulatory readiness.',
      location: 'Warsaw / Remote',
      url: 'https://geosync.dev/community/hubs/emea',
    },
  ],
  opportunities: [
    {
      title: 'Compliance automation squad',
      scope: 'Risk & controls',
      description: 'Ship analytics to visualise real-time exposure adjustments.',
      url: 'https://geosync.dev/community/opportunities/compliance',
    },
    {
      title: 'Mobile UX guild',
      scope: 'Product design',
      description: 'Adapt dashboards for native mobile workflows.',
      url: 'https://geosync.dev/community/opportunities/mobile',
    },
  ],
  champions: [
    {
      name: 'Ana López',
      contributions: 48,
      specialty: 'Data infrastructure',
      url: 'https://github.com/ana-lopez',
    },
    {
      name: 'Kenji Sato',
      contributions: 36,
      specialty: 'Execution engine',
      url: 'https://github.com/kenjisato',
    },
  ],
  channels: [
    { label: 'Slack', url: 'https://chat.geosync.dev' },
    { label: 'GitHub Discussions', url: 'https://github.com/geosync-ai/geosync/discussions' },
  ],
  primaryCta: { label: 'Contribution playbook', url: 'https://geosync.dev/docs/contribute' },
  secondaryCta: { url: 'https://chat.geosync.dev' },
};

const githubOverview = {
  organization: 'GeoSync',
  repository: 'GeoSync',
  url: 'https://github.com/geosync-ai/geosync',
  stars: 4820,
  stars_delta: 0.16,
  forks: 318,
  active_forks: 27,
  watchers: 950,
  watchers_growth: 0.08,
  contributors: 86,
  new_contributors_30d: 5,
  commits_30d: 182,
  prs: { merged_30d: 64, open: 7 },
  last_release: { tag: 'v2.4.0', published_at: '2024-11-18T12:00:00Z' },
  languages: [
    { name: 'Python', share: 0.46, color: '#3572A5' },
    { name: 'TypeScript', share: 0.32, color: '#3178c6' },
    { name: 'Rust', share: 0.12, color: '#dea584' },
  ],
  workflows: [
    {
      name: 'CI',
      badge:
        'https://img.shields.io/github/actions/workflow/status/geosync-ai/geosync/ci.yml?label=CI&logo=github',
      url: 'https://github.com/geosync-ai/geosync/actions/workflows/ci.yml',
    },
    {
      name: 'Quality gate',
      badge:
        'https://img.shields.io/github/actions/workflow/status/geosync-ai/geosync/quality.yml?label=Quality&logo=github',
      url: 'https://github.com/geosync-ai/geosync/actions/workflows/quality.yml',
    },
  ],
  quality: {
    metrics: {
      coverage: 0.982,
      uptime_90d: 0.9992,
      incidents_30d: 1,
      mttr_hours: 1.4,
      health_score: 0.92,
    },
    slo: {
      coverage: 0.98,
      uptime: 0.999,
    },
    status: 'Operational',
    last_audit: '2025-02-15T10:00:00Z',
  },
  community: communityProfile,
};

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

const signalEvents = [
  {
    event_id: 'signal-1',
    schema_version: '1',
    symbol: 'AAPL',
    timestamp: now - 15000,
    signal_type: 'momentum_breakout',
    strength: 0.85,
    direction: 'BUY',
    ttl_seconds: 600,
    metadata: { timeframe: '5m', regime: 'trend' },
  },
  {
    event_id: 'signal-2',
    schema_version: '1',
    symbol: 'MSFT',
    timestamp: now - 90000,
    signal_type: 'mean_reversion',
    strength: 0.35,
    direction: 'SELL',
    ttl_seconds: 30,
    metadata: { zscore: '1.2' },
  },
  {
    event_id: 'signal-3',
    schema_version: '1',
    symbol: 'GOOG',
    timestamp: now - 45000,
    signal_type: 'volatility_collapse',
    strength: 1.2,
    direction: 'FLAT',
    ttl_seconds: null,
    metadata: {},
  },
];

const monitoringTelemetry = {
  environment: 'prod',
  currency: 'USD',
  controls: {
    killSwitch: {
      enabled: false,
      changedAt: now - 120000,
      changedBy: 'ops@geosync.ai',
      reason: 'Quarterly drill reset',
    },
    circuitBreaker: {
      state: 'closed',
      triggeredAt: now - 720000,
      reason: 'PnL recovered within guardrail',
      cooldownSeconds: 900,
    },
  },
  metrics: {
    grossExposure: { value: 1250000, limit: 1500000 },
    drawdown: { value: -0.038, limit: -0.1 },
    openOrders: { value: 18, limit: 40 },
    rejectionRate: { value: 0.012, threshold: 0.05, window: '1h' },
    circuitTrips: { value: 1, threshold: 3, window: '1h' },
  },
  timeSeries: {
    exposure: [
      { timestamp: now - 3600000, value: 980000 },
      { timestamp: now - 1800000, value: 1120000 },
      { timestamp: now - 600000, value: 1195000 },
      { timestamp: now, value: 1250000 },
    ],
    drawdown: [
      { timestamp: now - 3600000, value: -0.045 },
      { timestamp: now - 1800000, value: -0.041 },
      { timestamp: now - 600000, value: -0.036 },
      { timestamp: now, value: -0.038 },
    ],
  },
  alerts: [
    {
      id: 'alert-1',
      severity: 'warning',
      message: 'PnL drawdown breached warning threshold at -4%',
      timestamp: now - 900000,
    },
    {
      id: 'alert-2',
      severity: 'critical',
      message: 'Manual override executed by ops<script>alert("x")</script>',
      timestamp: now - 300000,
    },
  ],
};

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

const monitoringView = renderMonitoringView(monitoringTelemetry);
assert.strictEqual(monitoringView.route, 'monitoring', 'monitoring view should expose monitoring route identifier');
assert.ok(monitoringView.html.includes('Risk Control Center'), 'monitoring view should include headline');
assert.ok(monitoringView.html.includes('tp-pill'), 'monitoring view should surface status pills for controls');
assert.ok(monitoringView.charts.exposure.points.length >= 1, 'monitoring view should expose exposure chart points');
assert.ok(
  monitoringView.html.includes('tp-live-table__table'),
  'monitoring view should render alerts table markup',
);
assert.ok(
  !monitoringView.html.includes('<script>alert("x")</script>'),
  'monitoring view should escape alert messages to prevent script injection',
);
assert.ok(
  monitoringView.html.includes('data-role="view-meta"'),
  'monitoring view should embed metadata payload for hydration',
);

console.log('monitoring view tests passed');

// --- Dashboard shell + views ----------------------------------------------------------------

const dashboardView = renderDashboard({
  route: 'positions',
  header: {
    title: 'Execution Control Center',
    subtitle: 'Live oversight across strategies.',
    tags: ['derivatives', 'equities'],
  },
  overview: { github: githubOverview },
  monitoring: monitoringTelemetry,
  positions: { fills: fillEvents, orders: orderEvents, ticks },
  orders: { orders: orderEvents, fills: fillEvents },
  pnl: { pnlPoints, quotes },
  signals: { signals: signalEvents },
  community: { community: communityProfile, github: githubOverview },
});

assert.ok(dashboardView.html.includes('PnL &amp; Quotes'), 'navigation should expose pnl route');
assert.ok(dashboardView.html.includes('Open Positions'), 'positions component should be rendered for active route');
assert.ok(dashboardView.styles.includes('.tp-live-table'), 'styles should include live table classes');
assert.strictEqual(dashboardView.styles, DASHBOARD_STYLES, 'render should expose shared stylesheet reference');
assert.strictEqual(dashboardView.route, 'positions');

const navigationLinks = (dashboardView.html.match(/<a class="tp-nav__link/g) || []).length;
assert.strictEqual(navigationLinks, 7, 'dashboard should render all navigation links');
assert.ok(dashboardView.html.includes('Signals'), 'navigation should expose signals route');
assert.ok(dashboardView.html.includes('Monitoring'), 'navigation should expose monitoring route');
assert.ok(dashboardView.html.includes('Community'), 'navigation should expose community route');
assert.ok(dashboardView.html.includes('Overview'), 'navigation should surface overview route');

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

const signalsView = renderSignalsView({ signals: signalEvents });
assert.ok(signalsView.html.includes('Signal Intelligence'), 'signals view should include heading');
const signalRows = signalsView.table.getSortedRows();
assert.ok(signalRows.length >= 3, 'signals table should surface all rows');
assert.ok(signalRows.some((row) => row.isActive), 'signals should mark active entries');
assert.ok(signalRows.some((row) => !row.isActive), 'signals should mark expired entries when ttl elapsed');
assert.ok(signalsView.summary.activeCount >= 1, 'summary should count active signals');
assert.ok(signalsView.html.includes('tp-meta-list'), 'signals view should render metadata chips');

const overviewView = renderOverviewView({ github: githubOverview });
assert.ok(overviewView.html.includes('Product Pulse'), 'overview view should include primary heading');
assert.ok(overviewView.html.includes('4,820'), 'overview view should format star totals');
assert.ok(overviewView.html.includes('tp-github-workflow'), 'overview view should surface GitHub badges');
assert.ok(overviewView.html.includes('Python'), 'overview view should list dominant languages');
assert.ok(!overviewView.html.includes('javascript:'), 'overview view should sanitize external links');
assert.ok(overviewView.html.includes('Open-source community'), 'overview view should include community spotlight panel');
assert.ok(overviewView.html.includes('Mentorship seats'), 'community spotlight should describe mentorship capacity');
assert.ok(overviewView.html.includes('Reliability guardrails'), 'overview view should render reliability panel');
assert.ok(overviewView.html.includes('98.2%'), 'quality panel should surface coverage percentage');
assert.ok(overviewView.html.includes('Operational'), 'quality panel should highlight status badge');
assert.ok(overviewView.html.includes('Last audit'), 'quality panel should include audit metadata');
assert.strictEqual(overviewView.github, githubOverview);

const overviewDashboard = renderDashboard({
  overview: { github: githubOverview },
  monitoring: monitoringTelemetry,
  positions: { fills: fillEvents, orders: orderEvents, ticks },
  orders: { orders: orderEvents, fills: fillEvents },
  pnl: { pnlPoints, quotes },
  signals: { signals: signalEvents },
  community: { community: communityProfile, github: githubOverview },
});
assert.strictEqual(overviewDashboard.route, 'overview', 'dashboard default route should highlight overview view');
assert.ok(overviewDashboard.html.includes('tp-hero'), 'overview dashboard render should include hero section');
assert.ok(overviewDashboard.html.includes('data-role="locale-select"'), 'dashboard should expose locale switcher control');
assert.ok(overviewDashboard.html.includes('data-role="locale-config"'), 'dashboard should embed locale configuration payload');
assert.ok(overviewDashboard.html.includes('data-locale="en-US"'), 'dashboard should tag root element with the active locale');
assert.ok(overviewDashboard.html.includes('dir="ltr"'), 'dashboard should surface locale reading direction');

const communityView = renderCommunityView({ community: communityProfile, github: githubOverview });
assert.ok(communityView.html.includes('Community Impact Center'), 'community view should include headline');
assert.ok(communityView.html.includes('185,000'), 'community metrics should format download counts');
assert.ok(communityView.html.includes('Mentorship sprint'), 'community view should list active programs');
assert.ok(communityView.html.includes('Ana López'), 'community view should highlight champions');
assert.ok(communityView.html.includes('Engagement timeline'), 'community view should render engagement timeline section');
assert.ok(communityView.html.includes('Regional hubs'), 'community view should surface regional hubs section');
assert.ok(communityView.html.includes('Contribution opportunities'), 'community view should list contribution opportunities');
assert.ok(communityView.html.includes('data-role="resource-filters"'), 'community view should render resource filters');
assert.ok(communityView.html.includes('data-filter="guides"'), 'resource filters should include normalised categories');
assert.ok(!communityView.html.includes('javascript:'), 'community view should sanitise external links');
assert.strictEqual(communityView.community, communityProfile);

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
assert.strictEqual(formatPercent(0.256), '25.6%');
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
