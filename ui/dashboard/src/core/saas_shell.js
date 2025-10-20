import { renderDashboard, DASHBOARD_STYLES } from './dashboard_ui.js';
import { escapeHtml } from './formatters.js';
import { SAAS_SHELL_STYLES } from '../styles/saas_shell.css.js';

const DEFAULT_PRODUCT = {
  name: 'TradePulse Platform',
  plan: 'Enterprise',
  modules: [
    { label: 'Execution Monitoring', badge: 'Live' },
    { label: 'Risk Analytics', badge: 'Realtime' },
    { label: 'Reporting', badge: 'Automated' },
  ],
  contactEmail: 'support@tradepulse.io',
  contactName: 'Customer Operations',
};

const DEFAULT_TENANT = {
  name: 'Global Macro Desk',
  slug: 'global-macro',
};

export const SAAS_PAGE_STYLES = [DASHBOARD_STYLES, SAAS_SHELL_STYLES].join('\n');

function safeJson(value) {
  return JSON.stringify(value, null, 0).replace(/</g, '\\u003C');
}

function buildBootScript({ routes, defaultRoute, analytics = {} }) {
  const routesPayload = safeJson(routes);
  const analyticsPayload = safeJson({
    endpoint: analytics.endpoint || null,
    traceparent: analytics.traceparent || null,
    release: analytics.release || null,
  });

  return `(() => {\n` +
    `  const routes = ${routesPayload};\n` +
    `  const defaultRoute = ${JSON.stringify(defaultRoute)};\n` +
    `  const dashboardRoot = document.querySelector('[data-tp-dashboard]');\n` +
    `  if (!dashboardRoot) { return; }\n` +
    `  const viewContainer = () => dashboardRoot.querySelector('[data-tp-view]');\n` +
    `  const setRoute = (name) => {\n` +
    `    const target = routes[name] || routes[defaultRoute];\n` +
    `    if (!target) { return; }\n` +
    `    const container = viewContainer();\n` +
    `    if (container) {\n` +
    `      container.innerHTML = target.html;\n` +
    `    }\n` +
    `    const links = dashboardRoot.querySelectorAll('[data-route]');\n` +
    `    links.forEach((link) => {\n` +
    `      const route = link.getAttribute('data-route');\n` +
    `      link.classList.toggle('tp-nav__link--active', route === target.route);\n` +
    `    });\n` +
    `  };\n` +
    `  const applyFromHash = () => {\n` +
    `    const hash = (window.location.hash || '').replace(/^#/, '');\n` +
    `    setRoute(hash || defaultRoute);\n` +
    `  };\n` +
    `  dashboardRoot.addEventListener('click', (event) => {\n` +
    `    const link = event.target.closest ? event.target.closest('[data-route]') : null;\n` +
    `    if (!link) { return; }\n` +
    `    const route = link.getAttribute('data-route');\n` +
    `    if (!route) { return; }\n` +
    `    event.preventDefault();\n` +
    `    if (route !== (window.location.hash || '').replace(/^#/, '')) {\n` +
    `      window.location.hash = route;\n` +
    `    } else {\n` +
    `      setRoute(route);\n` +
    `    }\n` +
    `  });\n` +
    `  window.addEventListener('hashchange', applyFromHash);\n` +
    `  applyFromHash();\n` +
    `  const analytics = ${analyticsPayload};\n` +
    `  if (analytics && analytics.endpoint) {\n` +
    `    try {\n` +
    `      const payload = {\n` +
    `        event: 'dashboard_loaded',\n` +
    `        route: (window.location.hash || '').replace(/^#/, '') || defaultRoute,\n` +
    `        timestamp: Date.now(),\n` +
    `        release: analytics.release,\n` +
    `      };\n` +
    `      const headers = { 'content-type': 'application/json' };\n` +
    `      if (analytics.traceparent) {\n` +
    `        headers.traceparent = analytics.traceparent;\n` +
    `      }\n` +
    `      fetch(analytics.endpoint, {\n` +
    `        method: 'POST',\n` +
    `        headers,\n` +
    `        body: JSON.stringify(payload),\n` +
    `        keepalive: true,\n` +
    `      }).catch(() => {});\n` +
    `    } catch (error) {\n` +
    `      console.error('Telemetry dispatch failed', error);\n` +
    `    }\n` +
    `  }\n` +
    `})();`;
}

function resolveModules(product) {
  const modules = Array.isArray(product?.modules) && product.modules.length ? product.modules : DEFAULT_PRODUCT.modules;
  return modules.slice(0, 6).map((module) => ({
    label: module.label || 'Module',
    badge: module.badge || null,
  }));
}

function resolveTenant(tenant = {}) {
  return {
    ...DEFAULT_TENANT,
    ...tenant,
  };
}

function resolveProduct(product = {}) {
  return {
    ...DEFAULT_PRODUCT,
    ...product,
  };
}

export function renderSaasPage({
  data = {},
  header = {},
  route = 'pnl',
  tenant: tenantInput = {},
  product: productInput = {},
  meta = {},
  analytics = {},
} = {}) {
  const tenant = resolveTenant(tenantInput);
  const product = resolveProduct(productInput);
  const dashboard = renderDashboard({
    route,
    positions: data.positions,
    orders: data.orders,
    pnl: data.pnl,
    header,
  });

  const routes = Object.fromEntries(
    Object.entries(dashboard.routes || {}).map(([name, view]) => [
      name,
      {
        html: view.html,
        title: view.title || name,
        route: view.route || name,
      },
    ]),
  );

  const bootScript = buildBootScript({
    routes,
    defaultRoute: dashboard.route,
    analytics,
  });

  const metaTitle = meta.title || `${product.name} • ${tenant.name}`;
  const metaDescription =
    meta.description ||
    'Operational intelligence for execution, risk, and performance – delivered as a secure SaaS dashboard.';

  const contactLabel = product.contactName || DEFAULT_PRODUCT.contactName;
  const contactEmail = product.contactEmail || DEFAULT_PRODUCT.contactEmail;

  const modules = resolveModules(product);

  const sidebarMenu = modules
    .map((module) => {
      const badge = module.badge
        ? `<span class="tp-saas__badge">${escapeHtml(module.badge)}</span>`
        : '';
      return `<li class="tp-saas__menu-item"><span>${escapeHtml(module.label)}</span>${badge}</li>`;
    })
    .join('');

  const html = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(metaTitle)}</title>
    <meta name="description" content="${escapeHtml(metaDescription)}" />
    <meta property="og:title" content="${escapeHtml(meta.title || metaTitle)}" />
    <meta property="og:description" content="${escapeHtml(metaDescription)}" />
    <style>${SAAS_PAGE_STYLES}</style>
  </head>
  <body class="tp-saas">
    <div class="tp-saas__layout">
      <aside class="tp-saas__sidebar">
        <div class="tp-saas__brand">
          <span class="tp-saas__logo">${escapeHtml(tenant.slug?.slice(0, 2).toUpperCase() || 'TP')}</span>
          <div class="tp-saas__tenant">
            <h1 class="tp-saas__tenant-name">${escapeHtml(tenant.name)}</h1>
            <p class="tp-saas__tenant-plan">${escapeHtml(product.plan)}</p>
          </div>
        </div>
        <ul class="tp-saas__menu">${sidebarMenu}</ul>
        <footer class="tp-saas__footer">
          <p>Secure tenancy: ${escapeHtml(tenant.slug)}</p>
          <p>Status: <span class="tp-saas__badge">Operational</span></p>
        </footer>
      </aside>
      <section class="tp-saas__workspace">
        <header class="tp-saas__topbar">
          <div class="tp-saas__topbar-actions">
            <span class="tp-saas__status">99.98% uptime</span>
            <button type="button" class="tp-saas__action">Launch API Console</button>
          </div>
          <div class="tp-saas__contact">
            <span class="tp-saas__contact-label">${escapeHtml(contactLabel)}</span>
            <a class="tp-saas__contact-link" href="mailto:${escapeHtml(contactEmail)}">${escapeHtml(contactEmail)}</a>
          </div>
        </header>
        <div class="tp-saas__dashboard" data-tp-dashboard>
          ${dashboard.html}
        </div>
      </section>
    </div>
    <script>${bootScript.replace(/<\/script/gi, '\u003C/script')}</script>
  </body>
</html>`;


  return {
    html,
    styles: SAAS_PAGE_STYLES,
    script: bootScript,
    dashboard,
    route: dashboard.route,
    meta: {
      title: metaTitle,
      description: metaDescription,
    },
  };
}
