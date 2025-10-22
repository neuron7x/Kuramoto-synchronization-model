import { createRouter } from '../router/index.js';
import { renderOrdersView } from '../views/orders.js';
import { renderOverviewView } from '../views/overview.js';
import { renderPnlQuotesView } from '../views/pnl_quotes.js';
import { renderPositionsView } from '../views/positions.js';
import { renderSignalsView } from '../views/signals.js';
import { escapeHtml, serializeForScript } from './formatters.js';
import { BASE_STYLES } from '../styles/base.css.js';
import { TABLE_STYLES } from '../styles/table.css.js';
import { CHART_STYLES } from '../styles/chart.css.js';
import { getMessage, t } from '../i18n/index.js';

export const DASHBOARD_STYLES = [BASE_STYLES, TABLE_STYLES, CHART_STYLES].join('\n');

function resolveHeaderDefaults({ title, subtitle, tags }) {
  const defaultTags = getMessage('header.tags') || [];
  return {
    title: title ?? t('header.title'),
    subtitle: subtitle ?? t('header.subtitle'),
    tags: Array.isArray(tags) ? tags : Array.from(defaultTags),
  };
}

function renderHeader({ title, subtitle, tags } = {}) {
  const resolved = resolveHeaderDefaults({ title, subtitle, tags });
  const tagMarkup = Array.isArray(resolved.tags)
    ? resolved.tags
        .filter((tag) => tag)
        .map((tag) => `<span class="tp-pill">${escapeHtml(String(tag))}</span>`)
        .join('')
    : '';
  const subtitleBlock = resolved.subtitle
    ? `<p class="tp-view__subtitle">${escapeHtml(String(resolved.subtitle))}</p>`
    : '';
  const metadataJson = serializeForScript({
    title: resolved.title ?? '',
    subtitle: resolved.subtitle ?? '',
    tags: Array.isArray(resolved.tags) ? resolved.tags.filter(Boolean) : [],
  });

  return `
    <header class="tp-view">
      <div class="tp-view__header">
        <h1 class="tp-view__title">${escapeHtml(String(resolved.title))}</h1>
        ${subtitleBlock}
      </div>
      <div class="tp-card__meta">${tagMarkup}</div>
      <script type="application/json" class="tp-view__meta" data-role="view-meta">${metadataJson}</script>
    </header>
  `;
}

function renderNavigation(router, currentRoute) {
  const sections = getMessage('nav.sections') || {};
  const liveBadge = t('nav.badges.live');
  const links = router.list().map((route) => {
    const label = sections[route] || route;
    const activeClass = route === currentRoute ? ' tp-nav__link--active' : '';
    const isActive = route === currentRoute;
    const ariaCurrent = isActive ? ' aria-current="page"' : '';
    const dataState = isActive ? ' data-state="active"' : '';
    return `
      <li>
        <a class="tp-nav__link${activeClass}" href="#${escapeHtml(route)}" data-route="${escapeHtml(route)}"${dataState}${ariaCurrent}>
          <span>${escapeHtml(String(label))}</span>
          <span class="tp-nav__badge">${escapeHtml(String(liveBadge))}</span>
        </a>
      </li>
    `;
  });

  return `
    <nav class="tp-nav" aria-label="Primary">
      <h2 class="tp-nav__title">${escapeHtml(String(t('nav.title')))}</h2>
      <ul class="tp-nav__links">${links.join('')}</ul>
    </nav>
  `;
}

function createDashboardRouter({ overview, positions, orders, pnl, signals }) {
  return createRouter({
    defaultRoute: 'overview',
    routes: {
      overview: () => renderOverviewView(overview),
      pnl: () => renderPnlQuotesView(pnl),
      positions: () => renderPositionsView(positions),
      orders: () => renderOrdersView(orders),
      signals: () => renderSignalsView(signals),
    },
  });
}

export function renderDashboard(options = {}) {
  const {
    route = 'overview',
    overview = {},
    positions = {},
    orders = {},
    pnl = {},
    signals = {},
    header = {},
  } = options;

  const router = createDashboardRouter({ overview, positions, orders, pnl, signals });
  const { name: currentRoute, view } = router.navigate(route);
  const navigation = renderNavigation(router, currentRoute);
  const headerHtml = renderHeader(header);

  const html = `
    <div class="tp-app">
      ${navigation}
      <main class="tp-shell">
        ${headerHtml}
        ${view.html}
      </main>
    </div>
  `;

  return {
    html,
    styles: DASHBOARD_STYLES,
    route: currentRoute,
    view,
  };
}
