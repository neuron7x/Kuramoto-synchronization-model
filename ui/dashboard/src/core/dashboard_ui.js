import { createRouter } from '../router/index.js';
import { renderOrdersView } from '../views/orders.js';
import { renderOverviewView } from '../views/overview.js';
import { renderPnlQuotesView } from '../views/pnl_quotes.js';
import { renderPositionsView } from '../views/positions.js';
import { renderSignalsView } from '../views/signals.js';
import { renderCommunityView } from '../views/community.js';
import { renderMonitoringView } from '../views/monitoring.js';
import { escapeHtml, serializeForScript } from './formatters.js';
import { BASE_STYLES } from '../styles/base.css.js';
import { TABLE_STYLES } from '../styles/table.css.js';
import { CHART_STYLES } from '../styles/chart.css.js';
import { ONBOARDING_STYLES } from '../styles/onboarding.css.js';
import { getMessage, t, getLocale, getLocaleConfig } from '../i18n/index.js';
import { renderOnboarding } from './onboarding.js';
import { supportedLocales, localeMetadata } from '../i18n/config.js';

/**
 * @typedef {import('../types/api').DashboardData} DashboardData
 * @typedef {import('../types/api').DashboardOverviewPayload} DashboardOverviewPayload
 * @typedef {import('../types/api').DashboardCommunityPayload} DashboardCommunityPayload
 */

export const DASHBOARD_STYLES = [BASE_STYLES, TABLE_STYLES, CHART_STYLES, ONBOARDING_STYLES].join('\n');

const FALLBACK_MENU_GROUPS = [
  {
    id: 'intelligence',
    label: 'Market intelligence',
    description: 'Monitor performance, profitability, and open risk.',
    items: ['overview', 'monitoring', 'pnl', 'positions'],
  },
  {
    id: 'execution',
    label: 'Execution oversight',
    description: 'Supervise orders and live trading directives.',
    items: ['orders', 'signals'],
  },
  {
    id: 'community',
    label: 'Community insights',
    description: 'Stay aligned with contributors and ecosystem health.',
    items: ['community'],
  },
];

const FALLBACK_TOOLBAR_ACTIONS = [
  {
    id: 'refresh',
    label: 'Refresh data',
    hint: 'Reload the latest telemetry for this view.',
    feedback: { success: 'Refreshing…', complete: 'Updated', error: 'Refresh failed' },
  },
  {
    id: 'export',
    label: 'Export report',
    hint: 'Download a JSON snapshot of the current context.',
    feedback: { success: 'Preparing…', complete: 'Exported', error: 'Export failed' },
  },
  {
    id: 'share',
    label: 'Share link',
    hint: 'Copy or share a link to this dashboard state.',
    feedback: { success: 'Copying…', complete: 'Link ready', error: 'Share failed' },
  },
];

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
      var navPanel = nav.querySelector('[data-role="nav-panel"]');
      var mainContent = document.querySelector('[data-role="main-content"]');
      var srLabel = toggle ? toggle.querySelector('.tp-nav__toggle-sr') : null;
      var openLabel = toggle ? toggle.getAttribute('data-open-label') || toggle.getAttribute('aria-label') || '' : '';
      var closeLabel = toggle ? toggle.getAttribute('data-close-label') || openLabel : openLabel;
      var app = document.querySelector('.tp-app');
      var localeSelect = document.querySelector('[data-role="locale-select"]');
      var localeConfigNode = document.querySelector('script[data-role="locale-config"]');
      var localeConfig = null;
      var toolbar = document.querySelector('[data-role="toolbar"]');
      var toolbarTimers = typeof WeakMap === 'function' ? new WeakMap() : null;
      var focusableSelectors = [
        'a[href]:not([tabindex="-1"])',
        'button:not([disabled]):not([tabindex="-1"])',
        'select:not([disabled]):not([tabindex="-1"])',
        'textarea:not([disabled]):not([tabindex="-1"])',
        'input:not([disabled]):not([tabindex="-1"])',
        '[tabindex]:not([tabindex="-1"])',
      ].join(',');
      var previousFocus = null;
      var mobileLayout = false;
      var layoutQuery = null;
      if (mainContent && !mainContent.hasAttribute('tabindex')) {
        mainContent.setAttribute('tabindex', '-1');
      }
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

      function isElementVisible(element) {
        if (!element) {
          return false;
        }
        if (element.hasAttribute && element.hasAttribute('disabled')) {
          return false;
        }
        if (element.getAttribute && element.getAttribute('aria-hidden') === 'true') {
          return false;
        }
        if (typeof element.getClientRects === 'function') {
          return element.getClientRects().length > 0;
        }
        return true;
      }

      function getFocusableElements() {
        var nodes = nav.querySelectorAll(focusableSelectors);
        return Array.prototype.filter.call(nodes, function (node) {
          return isElementVisible(node);
        });
      }

      function focusDefaultNavItem() {
        var activeLink = nav.querySelector('a[data-route][data-state="active"]');
        if (activeLink && typeof activeLink.focus === 'function') {
          activeLink.focus();
          return;
        }
        var focusable = getFocusableElements();
        if (focusable.length > 0 && typeof focusable[0].focus === 'function') {
          focusable[0].focus();
        }
      }

      function setState(open, options) {
        var opts = options || {};
        if (!mobileLayout) {
          open = true;
        }
        var nextState = open ? 'expanded' : 'collapsed';
        nav.setAttribute('data-state', nextState);
        if (toggle) {
          toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
          toggle.setAttribute('aria-label', open ? closeLabel : openLabel);
        }
        if (srLabel) {
          srLabel.textContent = open ? closeLabel : openLabel;
        }
        if (overlay) {
          var showOverlay = mobileLayout && open;
          overlay.hidden = !showOverlay;
          overlay.setAttribute('aria-hidden', showOverlay ? 'false' : 'true');
        }
        if (navPanel) {
          navPanel.setAttribute('aria-hidden', mobileLayout && !open ? 'true' : 'false');
        }
        if (!mobileLayout) {
          return;
        }
        if (open) {
          previousFocus = document.activeElement;
          if (!opts.preventAutoFocus) {
            focusDefaultNavItem();
          }
          return;
        }
        if (opts.skipFocusRestore) {
          previousFocus = null;
          return;
        }
        var focusTarget = opts.focusTarget && typeof opts.focusTarget.focus === 'function' ? opts.focusTarget : previousFocus;
        if (!focusTarget || typeof focusTarget.focus !== 'function') {
          focusTarget = toggle;
        }
        if (focusTarget && typeof focusTarget.focus === 'function') {
          focusTarget.focus();
        }
        previousFocus = null;
      }

      function handleFocusTrap(event) {
        if (!mobileLayout || nav.getAttribute('data-state') !== 'expanded') {
          return;
        }
        if (event.key !== 'Tab') {
          return;
        }
        var focusable = getFocusableElements();
        if (focusable.length === 0) {
          event.preventDefault();
          return;
        }
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        var activeElement = document.activeElement;
        if (event.shiftKey && activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && activeElement === last) {
          event.preventDefault();
          first.focus();
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

      function setToolbarButtonState(button, state) {
        if (!button) {
          return;
        }
        if (!state) {
          button.removeAttribute('data-state');
          button.removeAttribute('aria-busy');
          button.removeAttribute('disabled');
          return;
        }
        button.setAttribute('data-state', state);
        if (state === 'busy') {
          button.setAttribute('aria-busy', 'true');
          button.setAttribute('disabled', 'disabled');
        }
      }

      function setToolbarFeedback(button, message, options) {
        if (!button) {
          return;
        }
        var opts = options || {};
        if (!message) {
          button.removeAttribute('data-feedback');
          if (toolbarTimers && toolbarTimers.has(button)) {
            clearTimeout(toolbarTimers.get(button));
            toolbarTimers.delete(button);
          }
          return;
        }
        button.setAttribute('data-feedback', message);
        if (toolbarTimers) {
          var existingTimer = toolbarTimers.get(button);
          if (existingTimer) {
            clearTimeout(existingTimer);
          }
          if (opts.persistent) {
            toolbarTimers.delete(button);
            return;
          }
          var timeout = window.setTimeout(function () {
            button.removeAttribute('data-feedback');
            toolbarTimers.delete(button);
          }, typeof opts.duration === 'number' ? opts.duration : 2200);
          toolbarTimers.set(button, timeout);
        } else if (!opts.persistent) {
          window.setTimeout(function () {
            button.removeAttribute('data-feedback');
          }, typeof opts.duration === 'number' ? opts.duration : 2200);
        }
      }

      function getViewMetaPayload() {
        var node = document.querySelector('[data-role="view-meta"]');
        if (!node) {
          return null;
        }
        try {
          return JSON.parse(node.textContent || '{}');
        } catch (error) {
          if (typeof console !== 'undefined' && console.debug) {
            console.debug('Unable to parse view metadata', error);
          }
        }
        return null;
      }

      function exportCurrentViewReport() {
        var payload = getViewMetaPayload() || {};
        var route = payload && payload.route ? payload.route : toolbar ? toolbar.getAttribute('data-route') : '';
        var report = {
          route: route || null,
          generatedAt: new Date().toISOString(),
          payload: payload,
        };
        var blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = (route || 'dashboard') + '-report.json';
        document.body.appendChild(link);
        link.click();
        window.setTimeout(function () {
          if (link && link.parentNode) {
            link.parentNode.removeChild(link);
          }
          URL.revokeObjectURL(url);
        }, 0);
        return true;
      }

      function copyLinkToClipboard(url) {
        if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
          return navigator.clipboard
            .writeText(url)
            .then(function () {
              return true;
            })
            .catch(function () {
              return false;
            });
        }
        return new Promise(function (resolve) {
          try {
            var textArea = document.createElement('textarea');
            textArea.value = url;
            textArea.setAttribute('readonly', '');
            textArea.style.position = 'absolute';
            textArea.style.left = '-9999px';
            document.body.appendChild(textArea);
            textArea.select();
            textArea.setSelectionRange(0, textArea.value.length);
            var succeeded = false;
            try {
              succeeded = document.execCommand('copy');
            } catch (error) {
              succeeded = false;
            }
            document.body.removeChild(textArea);
            if (!succeeded) {
              try {
                window.prompt('Copy this link', url);
                resolve(true);
                return;
              } catch (promptError) {
                resolve(false);
                return;
              }
            }
            resolve(succeeded);
          } catch (error) {
            resolve(false);
          }
        });
      }

      function shareCurrentViewLink() {
        if (typeof window === 'undefined' || typeof window.location === 'undefined') {
          return Promise.resolve(false);
        }
        var shareUrl = window.location.href;
        if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
          return navigator
            .share({ title: document.title, url: shareUrl })
            .then(function () {
              return true;
            })
            .catch(function () {
              return copyLinkToClipboard(shareUrl);
            });
        }
        return copyLinkToClipboard(shareUrl);
      }

      function handleToolbarAction(action) {
        if (!action) {
          return Promise.resolve(false);
        }
        if (action === 'refresh') {
          return new Promise(function (resolve) {
            window.setTimeout(function () {
              resolve(true);
              window.location.reload();
            }, 120);
          });
        }
        if (action === 'export') {
          return new Promise(function (resolve, reject) {
            try {
              var result = exportCurrentViewReport();
              resolve(result);
            } catch (error) {
              reject(error);
            }
          });
        }
        if (action === 'share') {
          return shareCurrentViewLink();
        }
        try {
          if (typeof window !== 'undefined' && typeof window.CustomEvent === 'function') {
            var detail = { action: action };
            if (toolbar) {
              detail.route = toolbar.getAttribute('data-route') || null;
            }
            var dispatched = window.dispatchEvent(new CustomEvent('tp:toolbar-action', { detail: detail, bubbles: true }));
            return Promise.resolve(dispatched);
          }
        } catch (error) {
          return Promise.reject(error);
        }
        return Promise.resolve(false);
      }

      nav.setAttribute('data-enhanced', 'true');
      nav.addEventListener('keydown', handleFocusTrap);

      if (toolbar) {
        toolbar.addEventListener('click', function (event) {
          var button = event.target.closest('[data-action="toolbar-action"]');
          if (!button || button.disabled) {
            return;
          }
          var action = button.getAttribute('data-id');
          if (!action) {
            return;
          }
          event.preventDefault();
          var successLabel = button.getAttribute('data-success-label') || '';
          var completeLabel = button.getAttribute('data-complete-label') || '';
          var errorLabel = button.getAttribute('data-error-label') || '';
          setToolbarButtonState(button, 'busy');
          if (successLabel) {
            setToolbarFeedback(button, successLabel, { persistent: true });
          } else {
            setToolbarFeedback(button, '');
          }
          handleToolbarAction(action)
            .then(function (result) {
              setToolbarButtonState(button, '');
              setToolbarFeedback(button, '');
              var message = completeLabel || (result ? successLabel : '');
              if (!message && result) {
                message = 'Done';
              }
              if (message) {
                setToolbarFeedback(button, message);
              }
            })
            .catch(function (error) {
              setToolbarButtonState(button, '');
              setToolbarFeedback(button, '');
              var message = errorLabel || 'Failed';
              setToolbarFeedback(button, message, { duration: 3200 });
              if (typeof console !== 'undefined' && console.warn) {
                console.warn('Toolbar action failed', action, error);
              }
            });
        });
      }

      function updateLayoutFromQuery(event) {
        if (event && typeof event.matches === 'boolean') {
          mobileLayout = event.matches;
        } else if (layoutQuery) {
          mobileLayout = layoutQuery.matches;
        }
        setState(mobileLayout ? false : true, { skipFocusRestore: true, preventAutoFocus: true });
      }

      if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
        layoutQuery = window.matchMedia('(max-width: 1080px)');
        mobileLayout = layoutQuery.matches;
        updateLayoutFromQuery({ matches: mobileLayout });
        if (typeof layoutQuery.addEventListener === 'function') {
          layoutQuery.addEventListener('change', updateLayoutFromQuery);
        } else if (typeof layoutQuery.addListener === 'function') {
          layoutQuery.addListener(updateLayoutFromQuery);
        }
      } else {
        mobileLayout = toggle ? toggle.offsetParent !== null : false;
        setState(mobileLayout ? false : true, { skipFocusRestore: true, preventAutoFocus: true });
      }

      if (toggle) {
        toggle.addEventListener('click', function () {
          var isOpen = nav.getAttribute('data-state') === 'expanded';
          setState(!isOpen);
        });
      }

      if (overlay) {
        overlay.addEventListener('click', function () {
          if (mobileLayout) {
            setState(false);
          }
        });
      }

      closeButtons.forEach(function (button) {
        button.addEventListener('click', function () {
          if (mobileLayout) {
            setState(false);
          }
        });
      });

      links.forEach(function (link) {
        link.addEventListener('click', function () {
          if (mobileLayout) {
            setState(false, { focusTarget: mainContent });
          }
        });
      });

      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && mobileLayout && nav.getAttribute('data-state') === 'expanded') {
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

function resolveTranslationString(key, fallback = '') {
  const value = t(key);
  if (value == null) {
    return fallback;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed || trimmed === key) {
      return fallback;
    }
    return trimmed;
  }
  return fallback;
}

function toArray(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    return [value.trim()];
  }
  return [];
}

function normaliseMenuDefinition(router, sections) {
  const menuConfig = getMessage('nav.menu') || {};
  const availableRoutes = new Set(router.list());
  const normalisedGroups = [];

  const pushGroup = (id, rawGroup = {}) => {
    const groupId = typeof id === 'string' && id ? id : rawGroup.id || `group-${normalisedGroups.length + 1}`;
    const rawItems = toArray(rawGroup.items || rawGroup.routes);
    const routes = rawItems.filter((route) => availableRoutes.has(route));
    if (routes.length === 0) {
      return;
    }
    const labelSource = typeof rawGroup.label === 'string' && rawGroup.label.trim() !== ''
      ? rawGroup.label
      : sections[routes[0]] || routes[0];
    const descriptionSource = typeof rawGroup.description === 'string' ? rawGroup.description : '';
    normalisedGroups.push({
      id: groupId,
      label: labelSource,
      description: descriptionSource,
      routes,
    });
  };

  if (Array.isArray(menuConfig.groups)) {
    menuConfig.groups.forEach((group, index) => {
      pushGroup(group?.id || `group-${index + 1}`, group || {});
    });
  } else if (menuConfig.groups && typeof menuConfig.groups === 'object') {
    Object.entries(menuConfig.groups).forEach(([id, group]) => {
      pushGroup(id, group || {});
    });
  }

  if (normalisedGroups.length === 0) {
    FALLBACK_MENU_GROUPS.forEach((group) => {
      pushGroup(group.id, group);
    });
  }

  const titleSource = typeof menuConfig.title === 'string' && menuConfig.title.trim() !== ''
    ? menuConfig.title
    : resolveTranslationString('nav.menu.title', resolveTranslationString('nav.title', 'Navigation'));
  const descriptionSource = typeof menuConfig.description === 'string' && menuConfig.description.trim() !== ''
    ? menuConfig.description
    : '';

  return {
    title: titleSource,
    description: descriptionSource,
    groups: normalisedGroups,
  };
}

function normaliseToolbarDefinition() {
  const toolbarConfig = getMessage('nav.toolbar') || {};
  const normalisedActions = [];

  const pushAction = (id, rawAction = {}) => {
    const actionId = typeof id === 'string' && id ? id : rawAction.id;
    if (!actionId) {
      return;
    }
    const labelSource = typeof rawAction.label === 'string' && rawAction.label.trim() !== ''
      ? rawAction.label
      : actionId;
    const hintSource = typeof rawAction.hint === 'string' ? rawAction.hint : '';
    const feedback = rawAction.feedback && typeof rawAction.feedback === 'object' ? rawAction.feedback : {};
    normalisedActions.push({
      id: actionId,
      label: labelSource,
      hint: hintSource,
      feedback: {
        success: typeof feedback.success === 'string' ? feedback.success : '',
        complete: typeof feedback.complete === 'string' ? feedback.complete : '',
        error: typeof feedback.error === 'string' ? feedback.error : '',
      },
    });
  };

  if (Array.isArray(toolbarConfig.actions)) {
    toolbarConfig.actions.forEach((action) => {
      pushAction(action?.id, action || {});
    });
  } else if (toolbarConfig.actions && typeof toolbarConfig.actions === 'object') {
    Object.entries(toolbarConfig.actions).forEach(([id, action]) => {
      pushAction(id, action || {});
    });
  }

  if (normalisedActions.length === 0) {
    FALLBACK_TOOLBAR_ACTIONS.forEach((action) => pushAction(action.id, action));
  }

  const titleSource = typeof toolbarConfig.title === 'string' && toolbarConfig.title.trim() !== ''
    ? toolbarConfig.title
    : resolveTranslationString('nav.toolbar.title', 'Workspace actions');
  const descriptionSource = typeof toolbarConfig.description === 'string' && toolbarConfig.description.trim() !== ''
    ? toolbarConfig.description
    : '';

  return {
    title: titleSource,
    description: descriptionSource,
    actions: normalisedActions,
  };
}

function renderNavLink(route, sections, liveBadge, currentRoute) {
  const label = sections[route] || route;
  const activeClass = route === currentRoute ? ' tp-nav__link--active' : '';
  const isActive = route === currentRoute;
  const ariaCurrent = isActive ? ' aria-current="page"' : '';
  const dataState = isActive ? ' data-state="active"' : '';
  return `
      <li class="tp-nav__menu-item">
        <a class="tp-nav__link${activeClass}" href="#${escapeHtml(route)}" data-route="${escapeHtml(route)}"${dataState}${ariaCurrent}>
          <span class="tp-nav__link-label">${escapeHtml(String(label))}</span>
          <span class="tp-nav__badge">${escapeHtml(String(liveBadge))}</span>
        </a>
      </li>
    `;
}

function renderBreadcrumbs(route, meta = {}) {
  if (!route) {
    return '';
  }
  const currentRoute = route;
  const rootLabel = meta.breadcrumbRoot || resolveTranslationString('nav.title', 'Dashboard');
  const ariaLabel = meta.breadcrumbAria || 'Breadcrumb';
  const defaultRoute = meta.defaultRoute || 'overview';
  const currentLabel = meta.routeLabel || currentRoute;
  return `
    <nav class="tp-breadcrumbs" aria-label="${escapeHtml(String(ariaLabel))}">
      <ol class="tp-breadcrumbs__list">
        <li class="tp-breadcrumbs__item">
          <a class="tp-breadcrumbs__link" href="#${escapeHtml(defaultRoute)}" data-route="${escapeHtml(defaultRoute)}">
            ${escapeHtml(String(rootLabel))}
          </a>
        </li>
        <li class="tp-breadcrumbs__item" aria-current="page">
          <span class="tp-breadcrumbs__current">${escapeHtml(String(currentLabel))}</span>
        </li>
      </ol>
    </nav>
  `;
}

function renderToolbar({ route, routeLabel }) {
  const toolbar = normaliseToolbarDefinition();
  if (!toolbar.actions.length) {
    return { html: '', actions: [] };
  }
  const actions = toolbar.actions
    .map((action) => {
      const successLabel = action.feedback.success || '';
      const completeLabel = action.feedback.complete || '';
      const errorLabel = action.feedback.error || '';
      return `
        <button
          type="button"
          class="tp-toolbar__button"
          data-action="toolbar-action"
          data-id="${escapeHtml(action.id)}"
          data-route="${escapeHtml(route)}"
          ${successLabel ? `data-success-label="${escapeHtml(String(successLabel))}"` : ''}
          ${completeLabel ? `data-complete-label="${escapeHtml(String(completeLabel))}"` : ''}
          ${errorLabel ? `data-error-label="${escapeHtml(String(errorLabel))}"` : ''}
          aria-label="${escapeHtml(String(action.label))}"
        >
          <span class="tp-toolbar__button-label">${escapeHtml(String(action.label))}</span>
          ${action.hint ? `<span class="tp-toolbar__button-hint">${escapeHtml(String(action.hint))}</span>` : ''}
        </button>
      `;
    })
    .join('');

  const descriptionBlock = toolbar.description
    ? `<p class="tp-toolbar__description">${escapeHtml(String(toolbar.description))}</p>`
    : '';

  return {
    html: `
      <section class="tp-toolbar" data-role="toolbar" data-route="${escapeHtml(route)}">
        <div class="tp-toolbar__header">
          <div class="tp-toolbar__context">
            <p class="tp-toolbar__eyebrow">${escapeHtml(String(toolbar.title))}</p>
            <h2 class="tp-toolbar__title">${escapeHtml(String(routeLabel || route))}</h2>
          </div>
          ${descriptionBlock}
        </div>
        <div class="tp-toolbar__actions">${actions}</div>
      </section>
    `,
    actions: toolbar.actions,
  };
}

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
  const liveBadge = resolveTranslationString('nav.badges.live', 'Live');
  const brand = resolveTranslationString('nav.brand', 'TradePulse');
  const toggleLabel = resolveTranslationString('nav.controls.toggle.label', 'Menu');
  const toggleOpen = resolveTranslationString('nav.controls.toggle.open', 'Open navigation');
  const toggleClose = resolveTranslationString('nav.controls.toggle.close', 'Close navigation');
  const navTitle = resolveTranslationString('nav.title', brand);
  const navPanelId = 'tp-nav-panel';
  const overlayId = 'tp-nav-overlay';
  const menuDefinition = normaliseMenuDefinition(router, sections);
  const localeSwitcher = renderLocaleSwitcher(currentLocale);
  const defaultRoute = typeof router.defaultRoute === 'string' && router.defaultRoute.trim() !== ''
    ? router.defaultRoute
    : 'overview';
  const routeLabel = sections[currentRoute] || currentRoute;
  const breadcrumbsConfig = getMessage('nav.breadcrumbs') || {};
  const breadcrumbRoot = typeof breadcrumbsConfig.root === 'string' && breadcrumbsConfig.root.trim() !== ''
    ? breadcrumbsConfig.root
    : navTitle;
  const breadcrumbAria = typeof breadcrumbsConfig.ariaLabel === 'string' && breadcrumbsConfig.ariaLabel.trim() !== ''
    ? breadcrumbsConfig.ariaLabel
    : 'Breadcrumb';

  const menuGroups = menuDefinition.groups
    .map((group) => {
      const items = group.routes
        .map((route) => renderNavLink(route, sections, liveBadge, currentRoute))
        .join('');
      if (!items) {
        return '';
      }
      const description = group.description
        ? `<p class="tp-nav__menu-group-description">${escapeHtml(String(group.description))}</p>`
        : '';
      return `
        <section class="tp-nav__menu-group" data-menu-group="${escapeHtml(String(group.id))}">
          <header class="tp-nav__menu-group-header">
            <h3 class="tp-nav__menu-group-title">${escapeHtml(String(group.label))}</h3>
            ${description}
          </header>
          <ul class="tp-nav__links tp-nav__menu-links">${items}</ul>
        </section>
      `;
    })
    .filter(Boolean)
    .join('');

  const menuHeader = `
        <header class="tp-nav__menu-header">
          <h3 class="tp-nav__menu-title">${escapeHtml(String(menuDefinition.title || navTitle))}</h3>
          ${menuDefinition.description ? `<p class="tp-nav__menu-description">${escapeHtml(String(menuDefinition.description))}</p>` : ''}
        </header>
  `;

  return {
    markup: `
    <nav class="tp-nav" aria-label="Primary" data-role="primary-nav" data-state="expanded" data-enhanced="false" data-current-route="${escapeHtml(String(currentRoute))}">
      <div class="tp-nav__mobile-bar">
        <span class="tp-nav__brand">${escapeHtml(String(brand))}</span>
        <button
          type="button"
          class="tp-nav__toggle"
          data-action="toggle-nav"
          data-open-label="${escapeHtml(String(toggleOpen))}"
          data-close-label="${escapeHtml(String(toggleClose))}"
          aria-controls="${navPanelId}"
          aria-expanded="true"
          aria-label="${escapeHtml(String(toggleClose))}"
        >
          <span class="tp-nav__toggle-bars" aria-hidden="true"></span>
          <span class="tp-nav__toggle-text">${escapeHtml(String(toggleLabel))}</span>
          <span class="tp-nav__toggle-sr tp-sr-only">${escapeHtml(String(toggleClose))}</span>
        </button>
      </div>
      <div id="${navPanelId}" class="tp-nav__panel" data-role="nav-panel" aria-hidden="false">
        <div class="tp-nav__panel-header">
          <h2 class="tp-nav__title">${escapeHtml(String(navTitle))}</h2>
          <button type="button" class="tp-nav__close" data-action="close-nav" aria-label="${escapeHtml(String(toggleClose))}">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <section class="tp-nav__menu" data-role="nav-menu">
          ${menuHeader}
          <div class="tp-nav__menu-groups">${menuGroups}</div>
        </section>
        ${localeSwitcher.markup}
      </div>
      <div id="${overlayId}" class="tp-nav__overlay" data-role="nav-overlay" hidden aria-hidden="true"></div>
    </nav>
    `,
    locales: localeSwitcher.payload,
    meta: {
      route: currentRoute,
      routeLabel,
      defaultRoute,
      breadcrumbRoot,
      breadcrumbAria,
    },
  };
}

/**
 * @param {{
 *   overview?: DashboardOverviewPayload;
 *   monitoring?: import('../types/api').DashboardMonitoringPayload;
 *   positions?: unknown;
 *   orders?: unknown;
 *   pnl?: unknown;
 *   signals?: unknown;
 *   community?: DashboardCommunityPayload;
 * }} config
 */
function createDashboardRouter({ overview, monitoring, positions, orders, pnl, signals, community }) {
  return createRouter({
    defaultRoute: 'overview',
    routes: {
      overview: () => renderOverviewView(overview),
      monitoring: () => renderMonitoringView(monitoring),
      pnl: () => renderPnlQuotesView(pnl),
      positions: () => renderPositionsView(positions),
      orders: () => renderOrdersView(orders),
      signals: () => renderSignalsView(signals),
      community: () => renderCommunityView(community),
    },
  });
}

/**
 * @param {DashboardData} [options]
 */
export function renderDashboard(options = {}) {
  const {
    route = 'overview',
    overview = {},
    monitoring = {},
    positions = {},
    orders = {},
    pnl = {},
    signals = {},
    community = {},
    header = {},
    onboarding: onboardingConfig = {},
  } = options;

  const router = createDashboardRouter({ overview, monitoring, positions, orders, pnl, signals, community });
  const { name: currentRoute, view } = router.navigate(route);
  const locale = getLocale();
  const navigation = renderNavigation(router, currentRoute, locale);
  const routeLabel = navigation.meta ? navigation.meta.routeLabel : currentRoute;
  const breadcrumbsHtml = renderBreadcrumbs(currentRoute, navigation.meta);
  const toolbar = renderToolbar({ route: currentRoute, routeLabel });
  const headerHtml = renderHeader(header);
  const localeConfig = getLocaleConfig(locale) || {};
  const direction = localeConfig.direction || 'ltr';
  const skipLinkLabel = getMessage('nav.accessibility.skipLink') || 'Skip to main content';
  const onboardingUi = renderOnboarding(onboardingConfig);
  const localePayload = {
    current: locale,
    locales: navigation.locales,
  };

  const html = `
    <div class="tp-app" data-locale="${escapeHtml(locale)}" dir="${escapeHtml(direction)}">
      <a class="tp-skip-link" href="#tp-main-content">${escapeHtml(String(skipLinkLabel))}</a>
      ${navigation.markup}
      <main id="tp-main-content" class="tp-shell" tabindex="-1" data-role="main-content">
        ${breadcrumbsHtml}
        ${toolbar.html}
        ${headerHtml}
        ${view.html}
      </main>
      ${(onboardingUi.markup ?? '')}
    </div>
    <script type="application/json" data-role="locale-config">${serializeForScript(localePayload)}</script>
    ${NAVIGATION_ENHANCEMENT_SCRIPT}
    ${(onboardingUi.script ?? '')}
  `;

  return {
    html,
    styles: DASHBOARD_STYLES,
    route: currentRoute,
    view,
  };
}
