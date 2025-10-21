import { renderAreaChart } from '../components/area_chart.js';
import {
  escapeHtml,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatTimestamp,
  serializeForScript,
} from '../core/formatters.js';
import { t } from '../i18n/index.js';

/**
 * @typedef {import('../types/events').BarEvent} BarEvent
 * @typedef {import('../types/events').TickEvent} TickEvent
 */

function normalisePnlSeries(pnlPoints = [], currency = 'USD') {
  return pnlPoints.map((point) => ({
    timestamp: point.timestamp,
    value: Number.isFinite(point.value) ? point.value : 0,
    label: `${formatTimestamp(point.timestamp)} • ${formatCurrency(point.value, currency)}`,
  }));
}

function normaliseQuoteSeries(quotes = []) {
  return quotes
    .filter((tick) => Number.isFinite(tick?.last_price) || (Number.isFinite(tick?.bid_price) && Number.isFinite(tick?.ask_price)))
    .map((tick) => {
      const price = Number.isFinite(tick.last_price)
        ? tick.last_price
        : (tick.bid_price + tick.ask_price) / 2;
      return {
        timestamp: tick.timestamp,
        value: price,
        label: `${formatTimestamp(tick.timestamp)} • ${formatNumber(price, { maximumFractionDigits: 4 })}`,
      };
    });
}

function summarisePnl(points = [], currency = 'USD') {
  if (!points.length) {
    return { total: 0, change: 0, runRate: 0, formatted: {} };
  }
  const sorted = points.slice().sort((a, b) => a.timestamp - b.timestamp);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const elapsed = last.timestamp - first.timestamp || 1;
  const change = last.value - first.value;
  const runRate = change / (elapsed / (60 * 60 * 1000));
  const totalDisplay = formatCurrency(last.value, currency);
  const changeDisplay = formatCurrency(change, currency);
  const runRateDisplay = formatCurrency(runRate, currency);
  const changePercent = first.value !== 0 ? formatPercent(change / Math.abs(first.value)) : formatPercent(0);
  return {
    total: last.value,
    change,
    runRate,
    formatted: {
      total: totalDisplay,
      change: changeDisplay,
      changePercent,
      runRate: `${runRateDisplay}/h`,
      runRateValue: runRateDisplay,
    },
  };
}

function summariseQuotes(quotes = []) {
  if (!quotes.length) {
    return { last: 0, change: 0, changePercent: 0 };
  }
  const sorted = quotes.slice().sort((a, b) => a.timestamp - b.timestamp);
  const first = sorted[0].value;
  const last = sorted[sorted.length - 1].value;
  const change = last - first;
  return {
    last,
    change,
    changePercent: first !== 0 ? change / first : 0,
  };
}

export function renderPnlQuotesView({ pnlPoints = [], quotes = [], currency = 'USD' } = {}) {
  const pnlSeries = normalisePnlSeries(pnlPoints, currency);
  const quoteSeries = normaliseQuoteSeries(quotes);
  const pnlChart = renderAreaChart({ id: 'pnl', series: pnlSeries });
  const quoteChart = renderAreaChart({ id: 'quotes', series: quoteSeries });
  const pnlSummary = summarisePnl(pnlSeries, currency);
  const quoteSummary = summariseQuotes(quoteSeries);

  const pnlTotal = escapeHtml(pnlSummary.formatted?.total || formatCurrency(0, currency));
  const pnlDelta = escapeHtml(
    t('views.pnl.cards.pnl.delta', {
      value: pnlSummary.formatted?.change || formatCurrency(0, currency),
      percent: pnlSummary.formatted?.changePercent || formatPercent(0),
    })
  );
  const pnlRunRate = escapeHtml(
    t('views.pnl.cards.pnl.runRate', {
      value: pnlSummary.formatted?.runRateValue || formatCurrency(0, currency),
    })
  );
  const quoteLast = escapeHtml(formatNumber(quoteSummary.last, { maximumFractionDigits: 4 }));
  const quoteDelta = escapeHtml(
    t('views.pnl.cards.quotes.delta', {
      value: formatNumber(quoteSummary.change, { maximumFractionDigits: 4 }),
      percent: formatPercent(quoteSummary.changePercent),
    })
  );
  const metadata = serializeForScript({
    route: 'pnl',
    heading: t('views.pnl.heading'),
    summary: {
      pnl: {
        total: pnlSummary.total,
        change: pnlSummary.change,
        runRate: pnlSummary.runRate,
      },
      quotes: quoteSummary,
    },
  });

  return {
    route: 'pnl',
    title: t('views.pnl.title'),
    html: `
      <section class="tp-view">
        <header class="tp-view__header">
          <h2 class="tp-view__title">${escapeHtml(t('views.pnl.heading'))}</h2>
          <p class="tp-view__subtitle">${escapeHtml(t('views.pnl.subtitle'))}</p>
        </header>
        <section class="tp-grid tp-grid--two">
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(t('views.pnl.cards.pnl.title'))}</h3>
              <div class="tp-card__meta">
                <span class="tp-stat">${pnlTotal}</span>
                <span class="tp-stat tp-stat--muted">${pnlDelta}</span>
                <span class="tp-stat tp-stat--muted">${pnlRunRate}</span>
              </div>
            </header>
            ${pnlChart.html}
          </article>
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">${escapeHtml(t('views.pnl.cards.quotes.title'))}</h3>
              <div class="tp-card__meta">
                <span class="tp-stat">${quoteLast}</span>
                <span class="tp-stat tp-stat--muted">${quoteDelta}</span>
              </div>
            </header>
            ${quoteChart.html}
          </article>
        </section>
        <script type="application/json" class="tp-view__meta" data-role="view-meta">${metadata}</script>
      </section>
    `,
    charts: {
      pnl: pnlChart,
      quotes: quoteChart,
    },
  };
}
