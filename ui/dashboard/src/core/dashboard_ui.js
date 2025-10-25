import { createRouter } from '../router/index.js';
import { renderOrdersView } from '../views/orders.js';
import { renderOverviewView } from '../views/overview.js';
import { renderPnlQuotesView } from '../views/pnl_quotes.js';
import { renderPositionsView } from '../views/positions.js';
import { renderSignalsView } from '../views/signals.js';
import { renderCommunityView } from '../views/community.js';
import { escapeHtml, serializeForScript } from './formatters.js';
import { BASE_STYLES } from '../styles/base.css.js';
import { TABLE_STYLES } from '../styles/table.css.js';
import { CHART_STYLES } from '../styles/chart.css.js';
import { getMessage, t, getLocale, getLocaleConfig } from '../i18n/index.js';
import { supportedLocales, localeMetadata } from '../i18n/config.js';

export const DASHBOARD_STYLES = [BASE_STYLES, TABLE_STYLES, CHART_STYLES].join('\n');

const NAVIGATION_ENHANCEMENT_SCRIPT = `
  <script>
    (function () {
      if (typeof document === 'undefined') {
        return;
      }
      var nav = document.querySelector('[data-role="primary-nav"]');
      if (!nav) {
        return;
      }
      var toggle = nav.querySelector('[data-action="toggle-nav"]');
      var overlay = nav.querySelector('[data-role="nav-overlay"]');
      var closeButtons = nav.querySelectorAll('[data-action="close-nav"]');
      var links = nav.querySelectorAll('a[data-route]');
      var srLabel = toggle ? toggle.querySelector('.tp-nav__toggle-sr') : null;
      var openLabel = toggle ? toggle.getAttribute('data-open-label') || toggle.getAttribute('aria-label') || '' : '';
      var closeLabel = toggle ? toggle.getAttribute('data-close-label') || openLabel : openLabel;
      var app = document.querySelector('.tp-app');
      var localeSelect = document.querySelector('[data-role="locale-select"]');
      var localeConfigNode = document.querySelector('script[data-role="locale-config"]');
      var localeConfig = null;
      var LOCALE_STORAGE_KEY = 'tp:locale';
      var LOCALE_COOKIE_NAME = 'tp_locale';
      var LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year

      function persistLocalePreference(nextLocale) {
        try {
          if (window.localStorage) {
            window.localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale);
          }
        } catch (storageError) {
          if (typeof console !== 'undefined' && console.debug) {
            console.debug('Unable to persist locale preference (storage)', storageError);
          }
        }
        try {
          if (typeof document !== 'undefined') {
            document.cookie =
              LOCALE_COOKIE_NAME +
              '=' +
              encodeURIComponent(nextLocale) +
              ';path=/' +
              ';max-age=' +
              String(LOCALE_COOKIE_MAX_AGE) +
              ';SameSite=Lax';
          }
        } catch (cookieError) {
          if (typeof console !== 'undefined' && console.debug) {
            console.debug('Unable to persist locale preference (cookie)', cookieError);
          }
        }
      }

      function navigateWithLocale(nextLocale) {
        if (typeof window === 'undefined' || typeof window.location === 'undefined') {
          return false;
        }
        try {
          var url = new URL(window.location.href);
          if (url.searchParams) {
            var current = url.searchParams.get('locale');
            if (current === nextLocale) {
              window.location.reload();
              return true;
            }
            url.searchParams.set('locale', nextLocale);
            window.location.assign(url.toString());
            return true;
          }
        } catch (urlError) {
          if (typeof console !== 'undefined' && console.debug) {
            console.debug('Falling back to manual locale navigation', urlError);
          }
        }
        try {
          var href = window.location.href || '';
          var hashIndex = href.indexOf('#');
          var hash = hashIndex >= 0 ? href.slice(hashIndex) : '';
          var beforeHash = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
          var queryIndex = beforeHash.indexOf('?');
          var path = queryIndex >= 0 ? beforeHash.slice(0, queryIndex) : beforeHash;
          var search = queryIndex >= 0 ? beforeHash.slice(queryIndex + 1) : '';
          var segments = search ? search.split('&').filter(Boolean) : [];
          var replaced = false;
          segments = segments.map(function (segment) {
            var equalIndex = segment.indexOf('=');
            var key = equalIndex >= 0 ? decodeURIComponent(segment.slice(0, equalIndex)) : decodeURIComponent(segment);
            if (key === 'locale') {
              replaced = true;
              return 'locale=' + encodeURIComponent(nextLocale);
            }
            return segment;
          });
          if (!replaced) {
            segments.push('locale=' + encodeURIComponent(nextLocale));
          }
          var nextSearch = segments.length ? '?' + segments.join('&') : '';
          window.location.href = path + nextSearch + hash;
          return true;
        } catch (fallbackError) {
          if (typeof console !== 'undefined' && console.warn) {
            console.warn('Unable to adjust locale query parameter, reloading instead', fallbackError);
          }
          window.location.reload();
        }
        return false;
      }

      if (localeConfigNode) {
        try {
          localeConfig = JSON.parse(localeConfigNode.textContent || '{}');
          if (!window.tp) {
            window.tp = {};
          }
          window.tp.localeConfig = localeConfig.locales || {};
          if (typeof window.tp.setLocale !== 'function') {
            window.tp.setLocale = function (nextLocale) {
              persistLocalePreference(nextLocale);
              return nextLocale;
            };
          }
        } catch (error) {
          if (typeof console !== 'undefined' && console.warn) {
            console.warn('Unable to parse locale config payload', error);
          }
        }
      }

      function setState(open) {
        nav.setAttribute('data-state', open ? 'expanded' : 'collapsed');
        if (toggle) {
          toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
          toggle.setAttribute('aria-label', open ? closeLabel : openLabel);
        }
        if (srLabel) {
          srLabel.textContent = open ? closeLabel : openLabel;
        }
        if (overlay) {
          overlay.hidden = !open;
        }
      }

      function applyActiveFilter(container, filter) {
        if (!container) {
          return;
        }
        var targetId = container.getAttribute('data-target');
        var list = targetId ? document.getElementById(targetId) : null;
        if (!list) {
          return;
        }
        var items = list.querySelectorAll('[data-category]');
        var buttons = container.querySelectorAll('[data-action="filter-resources"]');
        buttons.forEach(function (button) {
          if (button.getAttribute('data-filter') === filter) {
            button.classList.add('tp-community__filter--active');
            button.setAttribute('aria-pressed', 'true');
          } else {
            button.classList.remove('tp-community__filter--active');
            button.setAttribute('aria-pressed', 'false');
          }
        });
        var normalised = filter && filter !== 'all' ? filter.toLowerCase() : 'all';
        items.forEach(function (item) {
          var category = (item.getAttribute('data-category') || '').toLowerCase();
          var shouldShow = normalised === 'all' || category === normalised;
          item.hidden = !shouldShow;
        });
        container.setAttribute('data-active-filter', filter);
      }

      function bindResourceFilters() {
        var containers = document.querySelectorAll('[data-role="resource-filters"]');
        containers.forEach(function (container) {
          if (!container || container.getAttribute('data-bound') === 'true') {
            return;
          }
          container.setAttribute('data-bound', 'true');
          var defaultFilter = container.getAttribute('data-default') || 'all';
          container.addEventListener('click', function (event) {
            var button = event.target.closest('[data-action="filter-resources"]');
            if (!button || button.disabled) {
              return;
            }
            var filter = button.getAttribute('data-filter') || 'all';
            applyActiveFilter(container, filter);
          });
          applyActiveFilter(container, defaultFilter);
        });
      }

      function applyLocaleDirection(locale) {
        if (!app || !localeConfig || !localeConfig.locales) {
          return;
        }
        var next = localeConfig.locales[locale];
        if (next && next.direction) {
          app.setAttribute('dir', next.direction);
        }
        if (locale) {
          app.setAttribute('data-locale', locale);
        }
      }

      nav.setAttribute('data-enhanced', 'true');
      setState(false);

      if (toggle) {
        toggle.addEventListener('click', function () {
          var isOpen = nav.getAttribute('data-state') === 'expanded';
          setState(!isOpen);
        });
      }

      if (overlay) {
        overlay.addEventListener('click', function () {
          setState(false);
        });
      }

      closeButtons.forEach(function (button) {
        button.addEventListener('click', function () {
          setState(false);
        });
      });

      links.forEach(function (link) {
        link.addEventListener('click', function () {
          setState(false);
        });
      });

      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          setState(false);
        }
      });

      bindResourceFilters();

      if (localeSelect) {
        localeSelect.addEventListener('change', function (event) {
          var nextLocale = event.target.value;
          try {
            if (window.tp && typeof window.tp.setLocale === 'function') {
              var resolved = window.tp.setLocale(nextLocale, { source: 'nav-switcher' });
              applyLocaleDirection(resolved || nextLocale);
            } else {
              persistLocalePreference(nextLocale);
              applyLocaleDirection(nextLocale);
            }
          } catch (error) {
            if (typeof console !== 'undefined' && console.warn) {
              console.warn('Failed to set locale preference', error);
            }
          }
          try {
            if (typeof window.CustomEvent === 'function') {
              window.dispatchEvent(new CustomEvent('tp:locale-change', { detail: { locale: nextLocale } }));
            }
          } catch (error) {
            if (typeof console !== 'undefined' && console.debug) {
              console.debug('Unable to broadcast locale change', error);
            }
          }
          if (window.tp && window.tp.reloadOnLocaleChange !== false) {
            navigateWithLocale(nextLocale);
          }
        });
      }
    })();
  </script>
`;

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

function normaliseLocaleConfig() {
  const locales = {};
  supportedLocales.forEach((code) => {
    const meta = localeMetadata[code] || {};
    locales[code] = {
      label: meta.displayName || code,
      direction: meta.direction || 'ltr',
    };
  });
  return locales;
}

function renderLocaleSwitcher(currentLocale) {
  if (!supportedLocales || supportedLocales.length <= 1) {
    return { markup: '', payload: {} };
  }

  const locales = normaliseLocaleConfig();
  const localeMessages = getMessage('nav.locales.items') || {};
  const title = getMessage('nav.locales.title') || 'Language';
  const helper = getMessage('nav.locales.helper') || '';

  const options = supportedLocales
    .map((code) => {
      const localeMeta = locales[code] || {};
      const label = localeMessages[code] || localeMeta.label || code;
      const isCurrent = code === currentLocale;
      const direction = localeMeta.direction || 'ltr';
      return `
        <option value="${escapeHtml(code)}"${isCurrent ? ' selected' : ''} data-direction="${escapeHtml(direction)}">
          ${escapeHtml(String(label))}
        </option>
      `;
    })
    .join('');

  const markup = `
    <div class="tp-nav__locale">
      <label class="tp-nav__locale-label" for="tp-locale-select">${escapeHtml(String(title))}</label>
      <select id="tp-locale-select" class="tp-nav__locale-select" data-role="locale-select" aria-label="${escapeHtml(
        String(title),
      )}">
        ${options}
      </select>
      ${helper ? `<p class="tp-nav__locale-helper">${escapeHtml(String(helper))}</p>` : ''}
    </div>
  `;

  return { markup, payload: locales };
}

function renderNavigation(router, currentRoute, currentLocale) {
  const sections = getMessage('nav.sections') || {};
  const liveBadge = t('nav.badges.live');
  const brand = t('nav.brand');
  const toggleLabel = t('nav.controls.toggle.label');
  const toggleOpen = t('nav.controls.toggle.open');
  const toggleClose = t('nav.controls.toggle.close');
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

  const localeSwitcher = renderLocaleSwitcher(currentLocale);

  return {
    markup: `
    <nav class="tp-nav" aria-label="Primary" data-role="primary-nav" data-state="expanded" data-enhanced="false">
      <div class="tp-nav__mobile-bar">
        <span class="tp-nav__brand">${escapeHtml(String(brand))}</span>
        <button
          type="button"
          class="tp-nav__toggle"
          data-action="toggle-nav"
          data-open-label="${escapeHtml(String(toggleOpen))}"
          data-close-label="${escapeHtml(String(toggleClose))}"
          aria-expanded="true"
          aria-label="${escapeHtml(String(toggleClose))}"
        >
          <span class="tp-nav__toggle-bars" aria-hidden="true"></span>
          <span class="tp-nav__toggle-text">${escapeHtml(String(toggleLabel))}</span>
          <span class="tp-nav__toggle-sr tp-sr-only">${escapeHtml(String(toggleClose))}</span>
        </button>
      </div>
      <div class="tp-nav__panel" data-role="nav-panel">
        <div class="tp-nav__panel-header">
          <h2 class="tp-nav__title">${escapeHtml(String(t('nav.title')))}</h2>
          <button type="button" class="tp-nav__close" data-action="close-nav" aria-label="${escapeHtml(String(toggleClose))}">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <ul class="tp-nav__links">${links.join('')}</ul>
        ${localeSwitcher.markup}
      </div>
      <div class="tp-nav__overlay" data-role="nav-overlay" hidden aria-hidden="true"></div>
    </nav>
    `,
    locales: localeSwitcher.payload,
  };
}

function createDashboardRouter({ overview, positions, orders, pnl, signals, community }) {
  return createRouter({
    defaultRoute: 'overview',
    routes: {
      overview: () => renderOverviewView(overview),
      pnl: () => renderPnlQuotesView(pnl),
      positions: () => renderPositionsView(positions),
      orders: () => renderOrdersView(orders),
      signals: () => renderSignalsView(signals),
      community: () => renderCommunityView(community),
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
    community = {},
    header = {},
  } = options;

  const router = createDashboardRouter({ overview, positions, orders, pnl, signals, community });
  const { name: currentRoute, view } = router.navigate(route);
  const locale = getLocale();
  const navigation = renderNavigation(router, currentRoute, locale);
  const headerHtml = renderHeader(header);
  const localeConfig = getLocaleConfig(locale) || {};
  const direction = localeConfig.direction || 'ltr';
  const localePayload = {
    current: locale,
    locales: navigation.locales,
  };

  const html = `
    <div class="tp-app" data-locale="${escapeHtml(locale)}" dir="${escapeHtml(direction)}">
      ${navigation.markup}
      <main class="tp-shell">
        ${headerHtml}
        ${view.html}
      </main>
    </div>
    <script type="application/json" data-role="locale-config">${serializeForScript(localePayload)}</script>
    ${NAVIGATION_ENHANCEMENT_SCRIPT}
  `;

  return {
    html,
    styles: DASHBOARD_STYLES,
    route: currentRoute,
    view,
  };
}
