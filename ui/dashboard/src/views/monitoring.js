import { renderAreaChart } from '../components/area_chart.js';
import {
  escapeHtml,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatTimestamp,
  serializeForScript,
} from '../core/formatters.js';
import { getMessage, t } from '../i18n/index.js';

const BOOLEAN_TRUE_VALUES = new Set(['true', 'yes', 'enabled', 'on', '1', 'active']);
const BOOLEAN_FALSE_VALUES = new Set(['false', 'no', 'disabled', 'off', '0', 'inactive']);

function translate(key, fallback = '') {
  const value = t(key);
  if (value == null || value === key) {
    return fallback;
  }
  return value;
}

function coerceNumber(value) {
  if (Number.isFinite(value)) {
    return Number(value);
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function coerceTimestamp(value) {
  const numeric = coerceNumber(value);
  if (numeric == null) {
    return null;
  }
  return numeric;
}

function coerceBoolean(value) {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    if (value === 1) {
      return true;
    }
    if (value === 0) {
      return false;
    }
  }
  if (typeof value === 'string') {
    const normalised = value.trim().toLowerCase();
    if (BOOLEAN_TRUE_VALUES.has(normalised)) {
      return true;
    }
    if (BOOLEAN_FALSE_VALUES.has(normalised)) {
      return false;
    }
  }
  return null;
}

function parseKillSwitchState(control = {}) {
  const explicit = coerceBoolean(control.enabled);
  if (explicit !== null) {
    return explicit;
  }
  const state = typeof control.state === 'string' ? control.state : control.status;
  if (typeof state === 'string') {
    const normalised = state.trim().toLowerCase();
    if (BOOLEAN_TRUE_VALUES.has(normalised) || ['enabled', 'armed'].includes(normalised)) {
      return true;
    }
    if (BOOLEAN_FALSE_VALUES.has(normalised) || ['disabled', 'disarmed'].includes(normalised)) {
      return false;
    }
  }
  return null;
}

function parseCircuitState(control = {}) {
  const state = typeof control.state === 'string' ? control.state : control.status;
  if (typeof state !== 'string') {
    return 'unknown';
  }
  const normalised = state.trim().toLowerCase().replace(/\s+/g, '_');
  if (['open', 'half_open', 'half-open', 'closed'].includes(normalised)) {
    return normalised.replace('-', '_');
  }
  return 'unknown';
}

function toneForKillSwitch(isEnabled) {
  if (isEnabled === true) {
    return 'negative';
  }
  if (isEnabled === false) {
    return 'positive';
  }
  return null;
}

function toneForCircuit(state) {
  if (state === 'open') {
    return 'negative';
  }
  if (state === 'closed') {
    return 'positive';
  }
  return null;
}

function toneForSeverity(severity) {
  if (severity === 'critical') {
    return 'negative';
  }
  if (severity === 'info') {
    return 'positive';
  }
  return null;
}

function toneToModifier(tone) {
  if (tone === 'negative') {
    return 'tp-pill--negative';
  }
  if (tone === 'positive') {
    return 'tp-pill--positive';
  }
  return '';
}

function formatSignedCurrency(value, currency) {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const absolute = formatCurrency(Math.abs(value), currency);
  if (value > 0) {
    return `+${absolute}`;
  }
  if (value < 0) {
    return `-${absolute}`;
  }
  return absolute;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '—';
  }
  if (seconds === 0) {
    return '0s';
  }
  const intervals = [
    { unit: 'h', value: 3600 },
    { unit: 'm', value: 60 },
    { unit: 's', value: 1 },
  ];
  const parts = [];
  let remaining = Math.round(seconds);
  intervals.forEach(({ unit, value }) => {
    if (remaining >= value) {
      const count = Math.floor(remaining / value);
      remaining -= count * value;
      parts.push(`${count}${unit}`);
    }
  });
  return parts.join(' ') || '0s';
}

function normaliseSeries(points = [], formatter = (value) => formatNumber(value, { maximumFractionDigits: 2 })) {
  return (Array.isArray(points) ? points : [])
    .map((point) => ({
      timestamp: coerceTimestamp(point?.timestamp),
      value: coerceNumber(point?.value),
    }))
    .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.value))
    .map((point) => ({
      timestamp: point.timestamp,
      value: point.value,
      label: `${formatTimestamp(point.timestamp)} • ${formatter(point.value)}`,
    }));
}

function computeTrend(points = []) {
  if (!points.length) {
    return null;
  }
  const sorted = points.slice().sort((a, b) => a.timestamp - b.timestamp);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (!Number.isFinite(first?.value) || !Number.isFinite(last?.value)) {
    return null;
  }
  return last.value - first.value;
}

function buildMetaList(items = []) {
  const entries = items
    .filter((item) => item && item.label)
    .map((item) => {
      if (item.value) {
        return `
          <span class="tp-meta-list__item">
            <span class="tp-meta-list__key">${escapeHtml(item.label)}</span>
            <span>${escapeHtml(item.value)}</span>
          </span>
        `;
      }
      return `<span class="tp-meta-list__item">${escapeHtml(item.label)}</span>`;
    })
    .join('');
  if (!entries) {
    return '';
  }
  return `<div class="tp-meta-list">${entries}</div>`;
}

function normaliseAlerts(alerts = []) {
  return (Array.isArray(alerts) ? alerts : [])
    .map((alert, index) => {
      const severityRaw = typeof alert?.severity === 'string' ? alert.severity : 'info';
      const severity = severityRaw.trim().toLowerCase();
      const timestamp = coerceTimestamp(alert?.timestamp);
      return {
        id: alert?.id || `alert-${index + 1}`,
        severity: ['info', 'warning', 'critical'].includes(severity) ? severity : 'info',
        message: typeof alert?.message === 'string' ? alert.message : '',
        timestamp,
      };
    });
}

function renderAlertsTable(alerts, translations) {
  const alertsTranslations = translations?.sections?.alerts || {};
  const columns = alertsTranslations.columns || {};
  const timestampLabel = columns.timestamp || 'Timestamp';
  const severityLabel = columns.severity || 'Severity';
  const messageLabel = columns.message || 'Message';
  const emptyLabel = alertsTranslations.empty || 'No active alerts';

  if (!alerts.length) {
    return `
      <div class="tp-live-table" role="region" aria-live="polite">
        <div class="tp-live-table__viewport" role="group" tabindex="0" aria-label="${escapeHtml(alertsTranslations.title || 'Alerts')}">
          <table class="tp-live-table__table" role="table">
            <thead class="tp-live-table__head">
              <tr class="tp-live-table__row">
                <th class="tp-live-table__header" scope="col">${escapeHtml(timestampLabel)}</th>
                <th class="tp-live-table__header" scope="col">${escapeHtml(severityLabel)}</th>
                <th class="tp-live-table__header" scope="col">${escapeHtml(messageLabel)}</th>
              </tr>
            </thead>
            <tbody class="tp-live-table__body">
              <tr class="tp-live-table__row tp-live-table__row--empty">
                <td class="tp-live-table__cell" colspan="3">${escapeHtml(emptyLabel)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  const rows = alerts
    .map((alert) => {
      const severityLabelKey = `views.monitoring.badges.severity.${alert.severity}`;
      const severityText = translate(severityLabelKey, alert.severity.toUpperCase());
      const toneModifier = toneToModifier(toneForSeverity(alert.severity));
      const timestamp = Number.isFinite(alert.timestamp) ? formatTimestamp(alert.timestamp) : '—';
      return `
        <tr class="tp-live-table__row" data-alert-id="${escapeHtml(alert.id)}">
          <td class="tp-live-table__cell">
            <time datetime="${escapeHtml(timestamp)}">${escapeHtml(timestamp)}</time>
          </td>
          <td class="tp-live-table__cell">
            <span class="tp-pill ${toneModifier}">${escapeHtml(severityText)}</span>
          </td>
          <td class="tp-live-table__cell">${escapeHtml(alert.message)}</td>
        </tr>
      `;
    })
    .join('');

  return `
    <div class="tp-live-table" role="region" aria-live="polite">
      <div class="tp-live-table__viewport" role="group" tabindex="0" aria-label="${escapeHtml(alertsTranslations.title || 'Alerts')}">
        <table class="tp-live-table__table" role="table">
          <thead class="tp-live-table__head">
            <tr class="tp-live-table__row">
              <th class="tp-live-table__header" scope="col">${escapeHtml(timestampLabel)}</th>
              <th class="tp-live-table__header" scope="col">${escapeHtml(severityLabel)}</th>
              <th class="tp-live-table__header" scope="col">${escapeHtml(messageLabel)}</th>
            </tr>
          </thead>
          <tbody class="tp-live-table__body">${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function normaliseMetricLabel(templateKey, fallback, params) {
  const translated = translate(templateKey, fallback);
  return translated.replace(/\{(\w+)\}/g, (_, key) => {
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      const value = params[key];
      return value == null ? '' : String(value);
    }
    return '';
  });
}

export function renderMonitoringView({
  environment = '',
  currency = 'USD',
  controls = {},
  metrics = {},
  timeSeries = {},
  alerts = [],
} = {}) {
  const translations = getMessage('views.monitoring') || {};
  const title = translations.title || 'Risk Monitoring';
  const heading = translations.heading || 'Risk Control Center';
  const subtitle = translations.subtitle || 'Track kill switch readiness, circuit breakers, and limit pressure in one view.';

  const killSwitchState = parseKillSwitchState(controls?.killSwitch || {});
  const killSwitchStatusKey = killSwitchState === true ? 'enabled' : killSwitchState === false ? 'disabled' : null;
  const killSwitchStatusLabel = killSwitchStatusKey
    ? translate(`views.monitoring.sections.controls.killSwitch.status.${killSwitchStatusKey}`, killSwitchStatusKey)
    : translate('views.monitoring.sections.controls.killSwitch.title', 'Kill switch');
  const killSwitchTone = toneForKillSwitch(killSwitchState);
  const killSwitchChangedAt = coerceTimestamp(controls?.killSwitch?.changedAt || controls?.killSwitch?.updatedAt);
  const killSwitchActor = typeof controls?.killSwitch?.changedBy === 'string'
    ? controls.killSwitch.changedBy
    : typeof controls?.killSwitch?.actor === 'string'
    ? controls.killSwitch.actor
    : '';
  const killSwitchReason = typeof controls?.killSwitch?.reason === 'string' ? controls.killSwitch.reason : '';

  const circuitState = parseCircuitState(controls?.circuitBreaker || {});
  const circuitStatusLabel = circuitState !== 'unknown'
    ? translate(`views.monitoring.sections.controls.circuitBreaker.status.${circuitState}`, circuitState)
    : translate('views.monitoring.sections.controls.circuitBreaker.title', 'Circuit breaker');
  const circuitTone = toneForCircuit(circuitState);
  const circuitTriggeredAt = coerceTimestamp(controls?.circuitBreaker?.triggeredAt || controls?.circuitBreaker?.lastTripAt);
  const circuitCooldown = coerceNumber(controls?.circuitBreaker?.cooldownSeconds || controls?.circuitBreaker?.cooldown);
  const circuitReason = typeof controls?.circuitBreaker?.reason === 'string'
    ? controls.circuitBreaker.reason
    : typeof controls?.circuitBreaker?.lastReason === 'string'
    ? controls.circuitBreaker.lastReason
    : '';

  const exposureSeries = normaliseSeries(timeSeries?.exposure || [], (value) => formatCurrency(value, currency));
  const drawdownSeries = normaliseSeries(timeSeries?.drawdown || [], (value) => formatPercent(value));

  const exposureTrend = computeTrend(exposureSeries);
  const drawdownTrend = computeTrend(drawdownSeries);

  const exposureValue = coerceNumber(metrics?.grossExposure?.value);
  const exposureLimit = coerceNumber(metrics?.grossExposure?.limit);

  const drawdownValue = coerceNumber(metrics?.drawdown?.value);
  const drawdownLimitRaw = coerceNumber(metrics?.drawdown?.limit);
  const drawdownLimit = drawdownLimitRaw != null ? Math.abs(drawdownLimitRaw) : null;

  const openOrdersValue = coerceNumber(metrics?.openOrders?.value);
  const rejectionRateValue = coerceNumber(metrics?.rejectionRate?.value);
  const circuitTripsValue = coerceNumber(metrics?.circuitTrips?.value);
  const circuitWindow = typeof metrics?.circuitTrips?.window === 'string' && metrics.circuitTrips.window.trim() !== ''
    ? metrics.circuitTrips.window.trim()
    : '1h';

  const alertsList = normaliseAlerts(alerts);

  const exposureChart = renderAreaChart({ id: 'monitoring-exposure', series: exposureSeries });
  const drawdownChart = renderAreaChart({ id: 'monitoring-drawdown', series: drawdownSeries });

  const exposureLimitLabel = exposureLimit != null
    ? normaliseMetricLabel(
        'views.monitoring.cards.exposure.limit',
        `Limit ${formatCurrency(exposureLimit, currency)}`,
        { value: formatCurrency(exposureLimit, currency) },
      )
    : 'Limit —';

  const exposureTrendLabel = Number.isFinite(exposureTrend)
    ? normaliseMetricLabel(
        'views.monitoring.cards.exposure.trend',
        `Δ ${formatSignedCurrency(exposureTrend, currency)}`,
        { value: formatSignedCurrency(exposureTrend, currency) },
      )
    : normaliseMetricLabel('views.monitoring.cards.exposure.trend', 'Δ —', { value: '—' });

  const drawdownLimitLabel = drawdownLimit != null
    ? normaliseMetricLabel(
        'views.monitoring.cards.drawdown.limit',
        `Guardrail ${formatPercent(drawdownLimit)}`,
        { value: formatPercent(drawdownLimit) },
      )
    : 'Guardrail —';

  const drawdownTrendLabel = Number.isFinite(drawdownTrend)
    ? normaliseMetricLabel(
        'views.monitoring.cards.drawdown.trend',
        `Δ ${formatPercent(drawdownTrend)}`,
        { value: formatPercent(drawdownTrend) },
      )
    : normaliseMetricLabel('views.monitoring.cards.drawdown.trend', 'Δ —', { value: '—' });

  const openOrdersLabel = Number.isFinite(openOrdersValue)
    ? normaliseMetricLabel(
        'views.monitoring.cards.orders.open',
        `${formatNumber(openOrdersValue, { maximumFractionDigits: 0 })} open orders`,
        { count: formatNumber(openOrdersValue, { maximumFractionDigits: 0 }) },
      )
    : normaliseMetricLabel('views.monitoring.cards.orders.open', '— open orders', { count: '—' });

  const rejectionRateLabel = Number.isFinite(rejectionRateValue)
    ? normaliseMetricLabel(
        'views.monitoring.cards.orders.rejections',
        `${formatPercent(rejectionRateValue)} rejection rate`,
        { rate: formatPercent(rejectionRateValue) },
      )
    : normaliseMetricLabel('views.monitoring.cards.orders.rejections', '— rejection rate', { rate: '—' });

  const circuitTripsLabel = Number.isFinite(circuitTripsValue)
    ? normaliseMetricLabel(
        'views.monitoring.cards.orders.trips',
        `${formatNumber(circuitTripsValue, { maximumFractionDigits: 0 })} trips (${circuitWindow})`,
        {
          count: formatNumber(circuitTripsValue, { maximumFractionDigits: 0 }),
          window: circuitWindow,
        },
      )
    : normaliseMetricLabel('views.monitoring.cards.orders.trips', `— trips (${circuitWindow})`, {
        count: '—',
        window: circuitWindow,
      });

  const metaChips = buildMetaList([
    environment
      ? {
          label: (translations.labels && translations.labels.environment) || 'Environment',
          value: environment,
        }
      : null,
    killSwitchStatusLabel
      ? {
          label: (translations.labels && translations.labels.killSwitch) || 'Kill switch',
          value: killSwitchStatusLabel,
        }
      : null,
    circuitStatusLabel
      ? {
          label: (translations.labels && translations.labels.circuitBreaker) || 'Circuit',
          value: circuitStatusLabel,
        }
      : null,
  ]);

  const killSwitchMeta = buildMetaList(
    [
      killSwitchChangedAt
        ? {
            label: translate('views.monitoring.sections.controls.killSwitch.changed', 'Updated {time}').replace(
              '{time}',
              formatTimestamp(killSwitchChangedAt),
            ),
          }
        : null,
      killSwitchActor
        ? {
            label: translate('views.monitoring.sections.controls.killSwitch.actor', 'By {actor}').replace(
              '{actor}',
              killSwitchActor,
            ),
          }
        : null,
      killSwitchReason
        ? {
            label: translate('views.monitoring.sections.controls.killSwitch.reason', 'Reason: {reason}').replace(
              '{reason}',
              killSwitchReason,
            ),
          }
        : null,
    ].filter(Boolean),
  );

  const circuitMeta = buildMetaList(
    [
      circuitTriggeredAt
        ? {
            label: translate('views.monitoring.sections.controls.circuitBreaker.trigger', 'Last trip {time}').replace(
              '{time}',
              formatTimestamp(circuitTriggeredAt),
            ),
          }
        : null,
      Number.isFinite(circuitCooldown)
        ? {
            label: translate('views.monitoring.sections.controls.circuitBreaker.cooldown', 'Cooldown {value}').replace(
              '{value}',
              formatDuration(circuitCooldown),
            ),
          }
        : null,
      circuitReason
        ? {
            label: translate('views.monitoring.sections.controls.circuitBreaker.reason', 'Reason: {reason}').replace(
              '{reason}',
              circuitReason,
            ),
          }
        : null,
    ].filter(Boolean),
  );

  const alertsMarkup = renderAlertsTable(alertsList, translations);

  const metadata = serializeForScript({
    route: 'monitoring',
    heading,
    environment,
    controls: {
      killSwitch: {
        enabled: killSwitchState,
        changedAt: killSwitchChangedAt,
        changedBy: killSwitchActor,
        reason: killSwitchReason,
      },
      circuitBreaker: {
        state: circuitState,
        triggeredAt: circuitTriggeredAt,
        cooldownSeconds: circuitCooldown,
        reason: circuitReason,
      },
    },
    metrics: {
      grossExposure: { value: exposureValue, limit: exposureLimit, trend: exposureTrend },
      drawdown: { value: drawdownValue, limit: drawdownLimitRaw, trend: drawdownTrend },
      orders: {
        open: openOrdersValue,
        rejectionRate: rejectionRateValue,
        circuitTrips: circuitTripsValue,
        window: circuitWindow,
      },
    },
    alerts: alertsList.map((alert) => ({ id: alert.id, severity: alert.severity, timestamp: alert.timestamp })),
  });

  const killSwitchPill = `
    <span class="tp-pill ${toneToModifier(killSwitchTone)}">${escapeHtml(killSwitchStatusLabel)}</span>
  `;

  const circuitPill = `
    <span class="tp-pill ${toneToModifier(circuitTone)}">${escapeHtml(circuitStatusLabel)}</span>
  `;

  const controlsTitle = translate('views.monitoring.sections.controls.title', 'Safety controls');
  const exposureCardTitle = translate('views.monitoring.cards.exposure.title', 'Gross exposure');
  const drawdownCardTitle = translate('views.monitoring.cards.drawdown.title', 'Daily drawdown');
  const ordersCardTitle = translate('views.monitoring.cards.orders.title', 'Order flow health');
  const trendsTitle = translate('views.monitoring.sections.trends.title', 'Trend telemetry');
  const exposureTrendTitle = translate('views.monitoring.sections.trends.exposure.title', 'Exposure timeline');
  const drawdownTrendTitle = translate('views.monitoring.sections.trends.drawdown.title', 'Drawdown timeline');
  const alertsTitle = translate('views.monitoring.sections.alerts.title', 'Alerts & overrides');

  return {
    route: 'monitoring',
    title,
    html: `
      <section class="tp-view" data-route="monitoring">
        <header class="tp-view__header">
          <h2 class="tp-view__title">${escapeHtml(heading)}</h2>
          <p class="tp-view__subtitle">${escapeHtml(subtitle)}</p>
          ${metaChips}
        </header>
        <section class="tp-grid tp-grid--two">
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(translate('views.monitoring.sections.controls.killSwitch.title', 'Kill switch'))}</h3>
              <div class="tp-card__meta">${killSwitchPill}</div>
            </header>
            ${killSwitchMeta}
          </article>
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(translate('views.monitoring.sections.controls.circuitBreaker.title', 'Circuit breaker'))}</h3>
              <div class="tp-card__meta">${circuitPill}</div>
            </header>
            ${circuitMeta}
          </article>
        </section>
        <section class="tp-grid tp-grid--three" aria-label="${escapeHtml(controlsTitle)}">
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(exposureCardTitle)}</h3>
              <div class="tp-card__meta">
                <span class="tp-stat">${escapeHtml(formatCurrency(exposureValue, currency))}</span>
                <span class="tp-stat tp-stat--muted">${escapeHtml(exposureLimitLabel)}</span>
                <span class="tp-stat tp-stat--muted">${escapeHtml(exposureTrendLabel)}</span>
              </div>
            </header>
          </article>
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(drawdownCardTitle)}</h3>
              <div class="tp-card__meta">
                <span class="tp-stat">${escapeHtml(formatPercent(drawdownValue ?? Number.NaN))}</span>
                <span class="tp-stat tp-stat--muted">${escapeHtml(drawdownLimitLabel)}</span>
                <span class="tp-stat tp-stat--muted">${escapeHtml(drawdownTrendLabel)}</span>
              </div>
            </header>
          </article>
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(ordersCardTitle)}</h3>
              <div class="tp-card__meta">
                <span class="tp-stat">${escapeHtml(openOrdersLabel)}</span>
                <span class="tp-stat tp-stat--muted">${escapeHtml(rejectionRateLabel)}</span>
                <span class="tp-stat tp-stat--muted">${escapeHtml(circuitTripsLabel)}</span>
              </div>
            </header>
          </article>
        </section>
        <section class="tp-grid tp-grid--two" aria-label="${escapeHtml(trendsTitle)}">
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(exposureTrendTitle)}</h3>
            </header>
            ${exposureChart.html}
          </article>
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(drawdownTrendTitle)}</h3>
            </header>
            ${drawdownChart.html}
          </article>
        </section>
        <section class="tp-card">
          <header class="tp-card__header">
            <h3 class="tp-card__title">${escapeHtml(alertsTitle)}</h3>
          </header>
          ${alertsMarkup}
        </section>
        <script type="application/json" class="tp-view__meta" data-role="view-meta">${metadata}</script>
      </section>
    `,
    charts: {
      exposure: exposureChart,
      drawdown: drawdownChart,
    },
  };
}
