import { createLiveTable } from '../components/live_table.js';
import {
  escapeHtml,
  formatNumber,
  formatPercent,
  formatTimestamp,
  serializeForScript,
} from '../core/formatters.js';
import { getMessage, t } from '../i18n/index.js';

/**
 * @typedef {import('../types/events').SignalEvent} SignalEvent
 */

function normalizeDirection(value) {
  const raw = String(value || '').toUpperCase();
  if (raw === 'BUY' || raw === 'SELL' || raw === 'FLAT') {
    return raw;
  }
  return 'FLAT';
}

function normaliseStrength(value) {
  if (!Number.isFinite(value)) {
    return 0;
  }
  const magnitude = Math.abs(value);
  if (!Number.isFinite(magnitude)) {
    return 0;
  }
  if (magnitude <= 1) {
    return magnitude;
  }
  // Signals can occasionally report strength in percent-style units.
  return Math.min(magnitude / 100, 1);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return '—';
  }
  const totalSeconds = Math.floor(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

function interpolate(template, params = {}) {
  return String(template || '').replace(/\{(\w+)\}/g, (_, placeholder) => {
    if (Object.prototype.hasOwnProperty.call(params, placeholder)) {
      const value = params[placeholder];
      return value == null ? '' : String(value);
    }
    return '';
  });
}

function translate(key, params = {}, fallback) {
  const value = t(key, params);
  if (value === key) {
    if (fallback !== undefined) {
      return interpolate(fallback, params);
    }
    return key;
  }
  return value;
}

function buildSignalRows(signals = []) {
  const now = Date.now();
  return signals
    .filter((signal) => signal && typeof signal === 'object')
    .map((signal) => {
      const timestamp = Number.isFinite(signal.timestamp) ? signal.timestamp : null;
      const ttlSeconds = Number.isFinite(signal.ttl_seconds) ? Math.max(signal.ttl_seconds, 0) : null;
      const expiresAt = timestamp !== null && ttlSeconds !== null ? timestamp + ttlSeconds * 1000 : null;
      const isActive = expiresAt === null ? true : expiresAt > now;
      const strength = Number.isFinite(signal.strength) ? signal.strength : 0;
      const metadata = signal.metadata && typeof signal.metadata === 'object' ? signal.metadata : {};
      const metadataEntries = Object.entries(metadata).filter(([, value]) => value !== null && value !== undefined && value !== '');

      return {
        ...signal,
        direction: normalizeDirection(signal.direction),
        strength,
        strengthNormalized: normaliseStrength(strength),
        timestamp,
        ttlSeconds,
        expiresAt,
        isActive,
        metadataEntries,
      };
    });
}

function summariseSignals(rows = []) {
  const summary = {
    counts: { BUY: 0, SELL: 0, FLAT: 0 },
    activeCount: 0,
    averageStrength: 0,
    maxStrength: 0,
    latestTimestamp: 0,
  };

  rows.forEach((row) => {
    summary.counts[row.direction] = (summary.counts[row.direction] || 0) + 1;
    if (row.isActive) {
      summary.activeCount += 1;
      summary.averageStrength += row.strengthNormalized;
      summary.maxStrength = Math.max(summary.maxStrength, row.strengthNormalized);
    }
    if (Number.isFinite(row.timestamp)) {
      summary.latestTimestamp = Math.max(summary.latestTimestamp, row.timestamp);
    }
  });

  if (summary.activeCount > 0) {
    summary.averageStrength /= summary.activeCount;
  }

  return summary;
}

function getTranslations() {
  const view = getMessage('views.signals') || {};
  return {
    title: view.title || 'Signals',
    heading: view.heading || 'Signals',
    subtitle: view.subtitle || '',
    cards: view.cards || {},
    table: view.table || {},
  };
}

function renderSummaryCards(summary, cardsTranslations) {
  const cards = cardsTranslations || {};

  const activeTotal = escapeHtml(
    translate(
      'views.signals.cards.active.total',
      { count: formatNumber(summary.activeCount) },
      cards.active?.total || '{count} active',
    ),
  );
  const lastTimestamp = summary.latestTimestamp
    ? formatTimestamp(summary.latestTimestamp)
    : null;
  const lastTimestampDisplay = lastTimestamp
    ? translate('views.signals.cards.active.updated', { time: lastTimestamp }, cards.active?.updated || 'Latest {time}')
    : translate('views.signals.cards.active.none', {}, cards.active?.none || 'No signals yet');
  const activeUpdated = escapeHtml(lastTimestampDisplay);

  const buyCount = formatNumber(summary.counts.BUY || 0, { maximumFractionDigits: 0 });
  const sellCount = formatNumber(summary.counts.SELL || 0, { maximumFractionDigits: 0 });
  const flatCount = formatNumber(summary.counts.FLAT || 0, { maximumFractionDigits: 0 });
  const netBias = (summary.counts.BUY || 0) - (summary.counts.SELL || 0);
  const biasRatio = escapeHtml(
    translate(
      'views.signals.cards.bias.ratio',
      {
        buy: buyCount,
        sell: sellCount,
        flat: flatCount,
      },
      cards.bias?.ratio || 'Buy {buy} / Sell {sell} / Flat {flat}',
    ),
  );
  const biasDelta = escapeHtml(
    translate(
      netBias >= 0 ? 'views.signals.cards.bias.netLong' : 'views.signals.cards.bias.netShort',
      {
        value: formatNumber(Math.abs(netBias), { maximumFractionDigits: 0 }),
      },
      netBias >= 0
        ? cards.bias?.netLong || 'Net long {value}'
        : cards.bias?.netShort || 'Net short {value}',
    ),
  );

  const averageConviction = escapeHtml(
    translate(
      'views.signals.cards.conviction.average',
      {
        value: formatPercent(summary.averageStrength),
      },
      cards.conviction?.average || 'Avg {value}',
    ),
  );
  const peakConviction = escapeHtml(
    translate(
      'views.signals.cards.conviction.peak',
      {
        value: formatPercent(summary.maxStrength),
      },
      cards.conviction?.peak || 'Peak {value}',
    ),
  );

  return `
    <section class="tp-grid tp-grid--three">
      <article class="tp-card">
        <header class="tp-card__header">
          <h3 class="tp-card__title">${escapeHtml(
            translate('views.signals.cards.active.title', {}, cards.active?.title || 'Active Signals'),
          )}</h3>
          <div class="tp-card__meta">
            <span class="tp-stat">${activeTotal}</span>
            <span class="tp-stat tp-stat--muted">${activeUpdated}</span>
          </div>
        </header>
      </article>
      <article class="tp-card">
        <header class="tp-card__header">
          <h3 class="tp-card__title">${escapeHtml(
            translate('views.signals.cards.bias.title', {}, cards.bias?.title || 'Directional Bias'),
          )}</h3>
          <div class="tp-card__meta">
            <span class="tp-stat">${biasRatio}</span>
            <span class="tp-stat tp-stat--muted">${biasDelta}</span>
          </div>
        </header>
      </article>
      <article class="tp-card">
        <header class="tp-card__header">
          <h3 class="tp-card__title">${escapeHtml(
            translate('views.signals.cards.conviction.title', {}, cards.conviction?.title || 'Conviction'),
          )}</h3>
          <div class="tp-card__meta">
            <span class="tp-stat">${averageConviction}</span>
            <span class="tp-stat tp-stat--muted">${peakConviction}</span>
          </div>
        </header>
      </article>
    </section>
  `;
}

function getTableConfig(rows, tableTranslations, pageSize) {
  const table = tableTranslations || {};
  const columns = table.columns || {};
  const badges = table.badges || {};
  const directionLabels = badges.direction || {};
  const statusLabels = badges.status || {};
  const empty = table.empty ?? 'No signals available.';

  const liveTable = createLiveTable({
    columns: [
      {
        id: 'timestamp',
        label: columns.timestamp || 'Timestamp',
        accessor: (row) => row.timestamp,
        formatter: (value) =>
          value ? `<time>${escapeHtml(formatTimestamp(value))}</time>` : `<span class="tp-text-subtle">${escapeHtml(String(empty))}</span>`,
        sortValue: (row) => row.timestamp || 0,
      },
      {
        id: 'symbol',
        label: columns.symbol || 'Symbol',
        accessor: (row) => row.symbol,
        formatter: (value) => `<strong>${escapeHtml(value)}</strong>`,
      },
      {
        id: 'direction',
        label: columns.direction || 'Direction',
        accessor: (row) => row.direction,
        formatter: (value) => {
          const key = normalizeDirection(value).toLowerCase();
          const tone = key === 'sell' ? 'negative' : key === 'buy' ? 'positive' : '';
          const label = directionLabels[key] || value;
          const toneClass = tone ? ` tp-pill--${tone}` : '';
          return `<span class="tp-pill${toneClass}">${escapeHtml(String(label || value || ''))}</span>`;
        },
      },
      {
        id: 'strength',
        label: columns.strength || 'Strength',
        accessor: (row) => row.strengthNormalized,
        formatter: (value, row) => {
          const percent = Math.round((row.strengthNormalized || 0) * 100);
          const label = formatPercent(row.strengthNormalized || 0);
          return `
            <div class="tp-progress">
              <span class="tp-progress__bar" style="width:${percent}%"></span>
              <span class="tp-progress__label">${escapeHtml(label)}</span>
            </div>
          `;
        },
        sortValue: (row) => row.strengthNormalized,
        align: 'right',
      },
      {
        id: 'signal_type',
        label: columns.signal_type || 'Type',
        accessor: (row) => row.signal_type,
        formatter: (value) => escapeHtml(value),
      },
      {
        id: 'ttlSeconds',
        label: columns.ttl || 'TTL',
        accessor: (row) => row.ttlSeconds,
        formatter: (value) => escapeHtml(formatDuration(value)),
        sortValue: (row) => row.ttlSeconds ?? 0,
        align: 'right',
      },
      {
        id: 'status',
        label: columns.status || 'Status',
        accessor: (row) => (row.isActive ? 'active' : 'expired'),
        formatter: (value, row) => {
          const key = row.isActive ? 'active' : 'expired';
          const tone = row.isActive ? 'positive' : 'negative';
          const label = statusLabels[key] || value;
          return `<span class="tp-pill tp-pill--${tone}">${escapeHtml(String(label || value || ''))}</span>`;
        },
      },
      {
        id: 'metadataEntries',
        label: columns.metadata || 'Context',
        accessor: (row) => row.metadataEntries,
        formatter: (entries) => {
          if (!Array.isArray(entries) || entries.length === 0) {
            return `<span class="tp-text-subtle">${escapeHtml(String(empty))}</span>`;
          }
          return `
            <div class="tp-meta-list">
              ${entries
                .map(([key, value]) => `
                  <span class="tp-meta-list__item">
                    <span class="tp-meta-list__key">${escapeHtml(String(key))}</span>
                    <span>${escapeHtml(String(value))}</span>
                  </span>
                `)
                .join('')}
            </div>
          `;
        },
      },
    ],
    rows,
    sortBy: 'timestamp',
    sortDirection: 'desc',
    pageSize,
  });

  return liveTable;
}

export function renderSignalsView({ signals = [], pageSize = 12, page = 1 } = {}) {
  const { heading, subtitle, cards, table, title } = getTranslations();
  const rows = buildSignalRows(signals);
  const summary = summariseSignals(rows);
  const liveTable = getTableConfig(rows, table, pageSize);
  const { html: tableHtml } = liveTable.render(page);
  const cardsHtml = renderSummaryCards(summary, cards);
  const metadata = serializeForScript({
    route: 'signals',
    summary,
    total: rows.length,
  });

  return {
    route: 'signals',
    title: title || 'Signals',
    html: `
      <section class="tp-view">
        <header class="tp-view__header">
          <h2 class="tp-view__title">${escapeHtml(heading)}</h2>
          <p class="tp-view__subtitle">${escapeHtml(subtitle)}</p>
        </header>
        ${cardsHtml}
        ${tableHtml}
        <script type="application/json" class="tp-view__meta" data-role="view-meta">${metadata}</script>
      </section>
    `,
    table: liveTable,
    rows,
    summary,
  };
}

