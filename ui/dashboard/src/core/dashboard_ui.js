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
  const toggleLabels = {
    menu: t('nav.toggle.menu'),
    open: t('nav.toggle.open'),
    close: t('nav.toggle.close'),
  };
  const toggleCopy = serializeForScript(toggleLabels);
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
    <nav class="tp-nav" aria-label="Primary" data-role="primary-nav" data-state="closed">
      <div class="tp-nav__brand">
        <h2 class="tp-nav__title">${escapeHtml(String(t('nav.title')))}</h2>
        <button class="tp-nav__toggle" type="button" data-role="nav-toggle" aria-expanded="false" aria-controls="tp-nav-links">
          <span class="tp-nav__toggle-icon" aria-hidden="true"><span></span><span></span><span></span></span>
          <span class="tp-nav__toggle-label" data-role="nav-toggle-label">${escapeHtml(String(toggleLabels.menu || t('nav.title')))}</span>
        </button>
      </div>
      <ul class="tp-nav__links" id="tp-nav-links">${links.join('')}</ul>
      <script type="application/json" data-role="nav-toggle-copy">${toggleCopy}</script>
    </nav>
    <script>
      (function attachTradePulseNavToggle() {
        if (typeof window === 'undefined' || typeof document === 'undefined') {
          return;
        }
        const nav = document.querySelector('[data-role="primary-nav"]');
        if (!nav) {
          return;
        }
        const toggle = nav.querySelector('[data-role="nav-toggle"]');
        const labelTarget = toggle ? toggle.querySelector('[data-role="nav-toggle-label"]') : null;
        const copyNode = nav.querySelector('script[data-role="nav-toggle-copy"]');
        let copy = { menu: 'Menu', open: 'Open navigation', close: 'Close navigation' };
        if (copyNode && copyNode.textContent) {
          try {
            const parsed = JSON.parse(copyNode.textContent);
            copy = { ...copy, ...parsed };
          } catch (error) {
            if (window?.console?.debug) {
              window.console.debug('Failed to parse navigation toggle copy', error);
            }
          }
        }

        function applyState(open) {
          const nextState = open ? 'open' : 'closed';
          nav.dataset.state = nextState;
          if (toggle) {
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
          }
          if (labelTarget) {
            const text = open ? (copy.close || copy.menu || copy.open) : (copy.open || copy.menu || copy.close);
            labelTarget.textContent = text;
          }
        }

        const mediaQuery = window.matchMedia('(min-width: 961px)');

        function syncForViewport(event) {
          const matches = typeof event?.matches === 'boolean' ? event.matches : mediaQuery.matches;
          if (matches) {
            applyState(true);
            if (labelTarget) {
              labelTarget.textContent = copy.menu || copy.close || copy.open;
            }
          } else if (nav.dataset.state !== 'open') {
            applyState(false);
          }
        }

        syncForViewport();
        if (typeof mediaQuery.addEventListener === 'function') {
          mediaQuery.addEventListener('change', syncForViewport);
        } else if (typeof mediaQuery.addListener === 'function') {
          mediaQuery.addListener(syncForViewport);
        }

        if (toggle) {
          toggle.addEventListener('click', () => {
            const isOpen = nav.dataset.state === 'open';
            applyState(!isOpen);
          });
        }

        const links = nav.querySelectorAll('a[data-route]');
        links.forEach((link) => {
          link.addEventListener('click', () => {
            if (window.matchMedia('(max-width: 960px)').matches) {
              applyState(false);
            }
          });
        });
      })();
    </script>
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
