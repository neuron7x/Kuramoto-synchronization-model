import { renderOverviewView } from '../views/overview.js';
import { renderMonitoringView } from '../views/monitoring.js';
import { renderPnlQuotesView } from '../views/pnl_quotes.js';
import { renderPositionsView } from '../views/positions.js';
import { renderOrdersView } from '../views/orders.js';
import { renderSignalsView } from '../views/signals.js';
import { renderCommunityView } from '../views/community.js';
import { renderBreadcrumbs, renderToolbar, renderHeader } from '../core/dashboard_ui.js';
import { injectSafeHtml } from '../core/sanitizer.js';
import DashboardDataClient from './data_client.js';

const VIEW_RENDERERS = {
  overview: renderOverviewView,
  monitoring: renderMonitoringView,
  pnl: renderPnlQuotesView,
  positions: renderPositionsView,
  orders: renderOrdersView,
  signals: renderSignalsView,
  community: renderCommunityView,
};

function getNavElement(root) {
  if (!root || typeof root.querySelector !== 'function') {
    return null;
  }
  return root.querySelector('[data-role="primary-nav"]');
}

function resolveRouteLabel(nav, route) {
  if (!nav) {
    return route;
  }
  const link = nav.querySelector(`a[data-route="${route}"]`);
  if (!link) {
    return route;
  }
  const labelNode = link.querySelector('.tp-nav__link-label');
  const text = labelNode ? labelNode.textContent : link.textContent;
  return typeof text === 'string' && text.trim() ? text.trim() : route;
}

function resolveBreadcrumbRoot(nav) {
  if (!nav) {
    return 'Dashboard';
  }
  const titleNode = nav.querySelector('.tp-nav__title');
  const text = titleNode ? titleNode.textContent : null;
  return typeof text === 'string' && text.trim() ? text.trim() : 'Dashboard';
}

function updateNavState(nav, route) {
  if (!nav) {
    return;
  }
  nav.setAttribute('data-current-route', route);
  const links = nav.querySelectorAll('a[data-route]');
  links.forEach((link) => {
    const linkRoute = link.getAttribute('data-route');
    const isActive = linkRoute === route;
    if (isActive) {
      link.setAttribute('data-state', 'active');
      link.classList.add('tp-nav__link--active');
      link.setAttribute('aria-current', 'page');
    } else {
      link.setAttribute('data-state', 'inactive');
      link.classList.remove('tp-nav__link--active');
      link.removeAttribute('aria-current');
    }
  });
}

function parseConfigPayload(node) {
  if (!node) {
    return {};
  }
  try {
    const raw = node.textContent || '{}';
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (error) {
    if (typeof console !== 'undefined' && console.warn) {
      console.warn('Unable to parse dashboard source configuration', error);
    }
  }
  return {};
}

function isPromise(value) {
  return value && typeof value.then === 'function';
}

export class DashboardApp {
  constructor({ root, client, initialRoute, header } = {}) {
    const resolvedRoot = root || (typeof document !== 'undefined' ? document.querySelector('.tp-app') : null);
    if (!resolvedRoot) {
      throw new Error('DashboardApp requires a root element to mount');
    }
    this.root = resolvedRoot;
    this.main = resolvedRoot.querySelector('[data-role="main-content"]');
    if (!this.main) {
      throw new Error('Dashboard main content container not found');
    }
    this.client = client || new DashboardDataClient({
      baseUrl: resolvedRoot.getAttribute('data-api-base') || '/',
      streamUrl: resolvedRoot.getAttribute('data-stream-url') || undefined,
    });
    this.state = {
      header: header || {},
      routes: {
        overview: {},
        monitoring: {},
        pnl: {},
        positions: {},
        orders: {},
        signals: {},
        community: {},
      },
      route: initialRoute || resolvedRoot.getAttribute('data-initial-route') || 'overview',
    };
    this.subscription = null;
    if (typeof window !== 'undefined') {
      window.tpDashboardApp = this;
    }
  }

  async start() {
    try {
      const snapshot = await this.client.fetchSnapshot();
      this._applySnapshot(snapshot);
      await this.renderRoute(this.state.route, { emitEvent: false });
      this._subscribe();
      return this;
    } catch (error) {
      this._handleRenderError(error);
      this._renderError(error);
      throw error;
    }
  }

  async refresh(route = this.state.route) {
    try {
      const response = await this.client.fetchRoute(route);
      const payload = response?.payload ?? response;
      this.state.routes[route] = payload;
      await this.renderRoute(route);
      return true;
    } catch (error) {
      this._handleRenderError(error);
      this._renderError(error);
      throw error;
    }
  }

  async navigate(route) {
    const targetRoute = route || this.state.route;
    if (targetRoute !== this.state.route) {
      this.state.route = targetRoute;
    }
    const result = await this.refresh(targetRoute);
    if (typeof window !== 'undefined' && window.location) {
      try {
        window.location.hash = `#${targetRoute}`;
      } catch (error) {
        // ignore navigation hash errors
      }
    }
    return result;
  }

  destroy() {
    if (this.subscription && typeof this.subscription.close === 'function') {
      this.subscription.close();
    }
    if (typeof window !== 'undefined' && window.tpDashboardApp === this) {
      delete window.tpDashboardApp;
    }
  }

  _applySnapshot(snapshot = {}) {
    const header = snapshot.header || {};
    const routes = {
      overview: snapshot.overview || this.state.routes.overview,
      monitoring: snapshot.monitoring || this.state.routes.monitoring,
      pnl: snapshot.pnl || this.state.routes.pnl,
      positions: snapshot.positions || this.state.routes.positions,
      orders: snapshot.orders || this.state.routes.orders,
      signals: snapshot.signals || this.state.routes.signals,
      community: snapshot.community || this.state.routes.community,
    };
    this.state.header = header;
    this.state.routes = routes;
    if (snapshot.route) {
      this.state.route = snapshot.route;
    }
  }

  async renderRoute(route, { payload, emitEvent = true } = {}) {
    const nav = getNavElement(this.root);
    const data = payload ?? this.state.routes[route] ?? {};
    this.state.routes[route] = data;
    this.state.route = route;

    const renderer = VIEW_RENDERERS[route] || VIEW_RENDERERS.overview;
    const view = renderer(data);
    const routeLabel = resolveRouteLabel(nav, route);
    const breadcrumbRoot = resolveBreadcrumbRoot(nav);
    const breadcrumbsHtml = renderBreadcrumbs(route, {
      routeLabel,
      breadcrumbRoot,
      defaultRoute: 'overview',
    });
    const toolbar = renderToolbar({ route, routeLabel });
    const headerHtml = renderHeader(this.state.header);
    const html = `${breadcrumbsHtml}${toolbar.html}${headerHtml}${view.html}`;
    injectSafeHtml(this.main, html);
    this.main.setAttribute('data-route', route);
    this.main.setAttribute('data-state', 'ready');
    if (this.root && typeof this.root.setAttribute === 'function') {
      this.root.setAttribute('data-state', 'ready');
    }

    if (window.tpDashboardRuntime && typeof window.tpDashboardRuntime.setActiveRoute === 'function') {
      window.tpDashboardRuntime.setActiveRoute(route);
    } else {
      updateNavState(nav, route);
    }

    if (emitEvent && typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('tp:view-updated', { detail: { route } }));
    }

    return view;
  }

  _subscribe() {
    if (!this.client || typeof this.client.subscribe !== 'function') {
      return;
    }
    this.subscription = this.client.subscribe({
      snapshot: (payload) => {
        this._applySnapshot(payload);
        this._invokeRender(() => this.renderRoute(this.state.route, { emitEvent: true }));
      },
      orders: (payload) => this._handleRouteUpdate('orders', payload),
      positions: (payload) => this._handleRouteUpdate('positions', payload),
      pnl: (payload) => this._handleRouteUpdate('pnl', payload),
      signals: (payload) => this._handleRouteUpdate('signals', payload),
      monitoring: (payload) => this._handleRouteUpdate('monitoring', payload),
    });
  }

  _handleRouteUpdate(route, payload) {
    this.state.routes[route] = payload;
    if (this.state.route === route) {
      this._invokeRender(() => this.renderRoute(route, { payload, emitEvent: true }));
    }
  }

  _invokeRender(operation) {
    try {
      const result = operation();
      if (isPromise(result)) {
        result.catch((error) => {
          this._handleRenderError(error);
        });
      }
    } catch (error) {
      this._handleRenderError(error);
    }
  }

  _renderError(error) {
    if (!this.main) {
      return;
    }
    const message =
      typeof error?.message === 'string' && error.message.trim() ? error.message.trim() : 'An unexpected error occurred.';
    const detailMarkup = message ? `<p class="tp-error__message">${message}</p>` : '';
    const markup = `
      <section class="tp-error" data-role="dashboard-error" role="alert">
        <h2 class="tp-error__title">Unable to load dashboard data</h2>
        ${detailMarkup}
        <p class="tp-error__hint">Please retry or contact support if the problem persists.</p>
      </section>
    `;
    injectSafeHtml(this.main, markup);
    this.main.setAttribute('data-state', 'error');
    if (this.root && typeof this.root.setAttribute === 'function') {
      this.root.setAttribute('data-state', 'error');
    }
  }

  _handleRenderError(error) {
    if (typeof console !== 'undefined' && console.error) {
      console.error('Dashboard render failed', error);
    }
  }

  static bootstrap(options = {}) {
    if (typeof document === 'undefined') {
      throw new Error('DashboardApp.bootstrap requires a browser environment');
    }
    const root = options.root || document.querySelector('.tp-app');
    if (!root) {
      throw new Error('Dashboard root element not found');
    }
    const configNode = document.querySelector('script[data-role="dashboard-source"]');
    const config = parseConfigPayload(configNode);
    const client = new DashboardDataClient({
      baseUrl: config.baseUrl || config.apiBaseUrl || config.base_url || root.getAttribute('data-api-base') || '/',
      streamUrl: config.streamUrl || config.stream_url || root.getAttribute('data-stream-url') || undefined,
      streamPath: config.streamPath || config.stream_path || undefined,
      requestInit: config.requestInit || {},
    });
    const app = new DashboardApp({
      root,
      client,
      initialRoute: config.route || root.getAttribute('data-initial-route') || undefined,
      header: config.header || undefined,
    });
    return app.start();
  }
}

export default DashboardApp;
