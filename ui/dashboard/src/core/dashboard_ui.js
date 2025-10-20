import { createRouter } from '../router/index.js';
import { renderOrdersView } from '../views/orders.js';
import { renderPnlQuotesView } from '../views/pnl_quotes.js';
import { renderPositionsView } from '../views/positions.js';
import { escapeHtml } from './formatters.js';
import { BASE_STYLES } from '../styles/base.css.js';
import { TABLE_STYLES } from '../styles/table.css.js';
import { CHART_STYLES } from '../styles/chart.css.js';

const DEFAULT_TITLE = 'TradePulse Monitoring Hub';
const DEFAULT_SUBTITLE = 'Unified control over execution, risk, and telemetry.';

export const DASHBOARD_STYLES = [BASE_STYLES, TABLE_STYLES, CHART_STYLES].join('\n');

function renderHeader({ title = DEFAULT_TITLE, subtitle = DEFAULT_SUBTITLE, tags = ['multi-asset', 'real-time'] } = {}) {
  const tagMarkup = Array.isArray(tags)
    ? tags
        .filter((tag) => tag)
        .map((tag) => `<span class="tp-pill">${escapeHtml(tag)}</span>`)
        .join('')
    : '';
  const subtitleBlock = subtitle
    ? `<p class="tp-view__subtitle">${escapeHtml(subtitle)}</p>`
    : '';

  return `
    <header class="tp-view">
      <div class="tp-view__header">
        <h1 class="tp-view__title">${escapeHtml(title)}</h1>
        ${subtitleBlock}
      </div>
      <div class="tp-card__meta">${tagMarkup}</div>
    </header>
  `;
}

function renderNavigation(router, currentRoute) {
  const labels = {
    positions: 'Positions',
    orders: 'Orders',
    pnl: 'PnL & Quotes',
  };

  const links = router.list().map((route) => {
    const label = labels[route] || route;
    const activeClass = route === currentRoute ? ' tp-nav__link--active' : '';
    return `
      <li>
        <a class="tp-nav__link${activeClass}" href="#${escapeHtml(route)}" data-route="${escapeHtml(route)}">
          <span>${escapeHtml(label)}</span>
          <span class="tp-nav__badge">Live</span>
        </a>
      </li>
    `;
  });

  return `
    <nav class="tp-nav" aria-label="Primary">
      <h2 class="tp-nav__title">TradePulse</h2>
      <ul class="tp-nav__links">${links.join('')}</ul>
    </nav>
  `;
}

function createDashboardRouter({ positions, orders, pnl }) {
  return createRouter({
    defaultRoute: 'pnl',
    routes: {
      positions: () => renderPositionsView(positions),
      orders: () => renderOrdersView(orders),
      pnl: () => renderPnlQuotesView(pnl),
    },
  });
}

export function renderDashboard(options = {}) {
  const {
    route = 'pnl',
    positions = {},
    orders = {},
    pnl = {},
    header = {},
  } = options;

  const router = createDashboardRouter({ positions, orders, pnl });
  const { name: currentRoute, view } = router.navigate(route);
  const cachedViews = new Map([[currentRoute, view]]);
  router.list().forEach((name) => {
    if (!cachedViews.has(name)) {
      const resolved = router.resolve(name);
      cachedViews.set(name, resolved.view);
    }
  });
  router.currentRoute = currentRoute;
  const navigation = renderNavigation(router, currentRoute);
  const headerHtml = renderHeader(header);

  const html = `
    <div class="tp-app">
      ${navigation}
      <main class="tp-shell">
        ${headerHtml}
        <div data-tp-view>${view.html}</div>
      </main>
    </div>
  `;

  return {
    html,
    styles: DASHBOARD_STYLES,
    route: currentRoute,
    view,
    routes: Object.fromEntries(
      Array.from(cachedViews.entries()).map(([name, entry]) => [
        name,
        {
          html: entry.html,
          title: entry.title,
          route: entry.route || name,
        },
      ]),
    ),
  };
}
