import { renderAreaChart } from '../components/area_chart.js';
import {
  escapeHtml,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatTimestamp,
} from '../core/formatters.js';

/**
 * @typedef {import('../types/events').BarEvent} BarEvent
 * @typedef {import('../types/events').TickEvent} TickEvent
 */

function normalisePnlSeries(pnlPoints = [], currency = 'USD', localization) {
  return pnlPoints.map((point) => ({
    timestamp: point.timestamp,
    value: Number.isFinite(point.value) ? point.value : 0,
    label: `${formatTimestamp(point.timestamp, localization)} • ${formatCurrency(point.value, currency, localization)}`,
  }));
}

function normaliseQuoteSeries(quotes = [], localization) {
  return quotes
    .filter((tick) => Number.isFinite(tick?.last_price) || (Number.isFinite(tick?.bid_price) && Number.isFinite(tick?.ask_price)))
    .map((tick) => {
      const price = Number.isFinite(tick.last_price)
        ? tick.last_price
        : (tick.bid_price + tick.ask_price) / 2;
      return {
        timestamp: tick.timestamp,
        value: price,
        label: `${formatTimestamp(tick.timestamp, localization)} • ${formatNumber(price, { maximumFractionDigits: 4 }, localization)}`,
      };
    });
}

function summarisePnl(points = [], currency = 'USD', localization) {
  if (!points.length) {
    return { total: 0, change: 0, runRate: 0 };
  }
  const sorted = points.slice().sort((a, b) => a.timestamp - b.timestamp);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const elapsed = last.timestamp - first.timestamp || 1;
  const change = last.value - first.value;
  const runRate = change / (elapsed / (60 * 60 * 1000));
  return {
    total: last.value,
    change,
    runRate,
    formatted: {
      total: formatCurrency(last.value, currency, localization),
      change: formatCurrency(change, currency, localization),
      runRate: `${formatCurrency(runRate, currency, localization)}/h`,
      changePercent:
        first.value !== 0
          ? formatPercent(change / Math.abs(first.value), localization)
          : formatPercent(0, localization),
    },
  };
}

function summariseQuotes(quotes = [], localization) {
  if (!quotes.length) {
    return { last: 0, change: 0 };
  }
  const sorted = quotes.slice().sort((a, b) => a.timestamp - b.timestamp);
  const first = sorted[0].value;
  const last = sorted[sorted.length - 1].value;
  const change = last - first;
  return {
    last,
    change,
    changePercent: first !== 0 ? change / first : 0,
    formatted: {
      last: formatNumber(last, { maximumFractionDigits: 4 }, localization),
      change: formatNumber(change, { maximumFractionDigits: 4 }, localization),
      changePercent: formatPercent(first !== 0 ? change / first : 0, localization),
    },
  };
}

export function renderPnlQuotesView({ pnlPoints = [], quotes = [], currency, localization } = {}) {
  const contextCurrency = currency || localization?.currency || 'USD';
  const pnlSeries = normalisePnlSeries(pnlPoints, contextCurrency, localization);
  const quoteSeries = normaliseQuoteSeries(quotes, localization);
  const pnlChart = renderAreaChart({ id: 'pnl', series: pnlSeries });
  const quoteChart = renderAreaChart({ id: 'quotes', series: quoteSeries });
  const pnlSummary = summarisePnl(pnlSeries, contextCurrency, localization);
  const quoteSummary = summariseQuotes(quoteSeries, localization);

  return {
    route: 'pnl',
    title: 'PnL & Quotes',
    html: `
      <section class="tp-view">
        <header class="tp-view__header">
          <h2 class="tp-view__title">PnL & Quotes Intelligence</h2>
          <p class="tp-view__subtitle">Cross-reference live profitability against streaming market data.</p>
        </header>
        <section class="tp-grid tp-grid--two">
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">Net PnL</h3>
              <div class="tp-card__meta">
                <span class="tp-stat">${escapeHtml(pnlSummary.formatted?.total || formatCurrency(0, contextCurrency, localization))}</span>
                <span class="tp-stat tp-stat--muted">Δ ${escapeHtml(
                  pnlSummary.formatted?.change || formatCurrency(0, contextCurrency, localization),
                )} (${escapeHtml(pnlSummary.formatted?.changePercent || formatPercent(0, localization))})</span>
                <span class="tp-stat tp-stat--muted">Run-rate ${escapeHtml(
                  pnlSummary.formatted?.runRate || `${formatCurrency(0, contextCurrency, localization)}/h`,
                )}</span>
              </div>
            </header>
            ${pnlChart.html}
          </article>
          <article class="tp-card">
            <header class="tp-card__header">
              <h3 class="tp-card__title">Quotes</h3>
              <div class="tp-card__meta">
                <span class="tp-stat">${escapeHtml(
                  quoteSummary.formatted?.last ||
                    formatNumber(quoteSummary.last, { maximumFractionDigits: 4 }, localization),
                )}</span>
                <span class="tp-stat tp-stat--muted">Δ ${escapeHtml(
                  quoteSummary.formatted?.change ||
                    formatNumber(quoteSummary.change, { maximumFractionDigits: 4 }, localization),
                )} (${escapeHtml(
                  quoteSummary.formatted?.changePercent || formatPercent(quoteSummary.changePercent, localization),
                )})</span>
              </div>
            </header>
            ${quoteChart.html}
          </article>
        </section>
      </section>
    `,
    charts: {
      pnl: pnlChart,
      quotes: quoteChart,
    },
  };
}
