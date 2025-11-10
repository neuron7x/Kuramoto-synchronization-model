import { sanitizeReportValue } from './formatters.js';

const DEFAULT_METRIC = 'sharpe';

export function createStrategyConfigurator(strategies = []) {
  const state = new Map();
  strategies.forEach((strategy) => {
    if (!strategy?.name) {
      throw new Error('Every strategy requires a name');
    }
    state.set(strategy.name, { ...(strategy.defaults || {}) });
  });

  function cloneParams(params) {
    return JSON.parse(JSON.stringify(params || {}));
  }

  return {
    list() {
      return Array.from(state.entries()).map(([name, params]) => ({
        name,
        params: cloneParams(params),
      }));
    },
    get(name) {
      if (!state.has(name)) {
        throw new Error(`Unknown strategy: ${name}`);
      }
      return cloneParams(state.get(name));
    },
    update(name, updates) {
      if (!state.has(name)) {
        throw new Error(`Unknown strategy: ${name}`);
      }
      const current = state.get(name);
      const next = { ...current, ...(updates || {}) };
      state.set(name, next);
      return cloneParams(next);
    },
  };
}

function normaliseMetricValue(value) {
  if (Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return Number.NEGATIVE_INFINITY;
}

export function compareBacktests(backtests = [], metric = DEFAULT_METRIC) {
  const enriched = backtests.map((entry) => {
    const meta = entry?.metadata || {};
    const metrics = entry?.metrics || {};
    const score = normaliseMetricValue(metrics[metric]);
    return {
      id: meta.id || entry?.id || meta.label || `backtest-${Math.random().toString(16).slice(2)}`,
      strategy: meta.strategy || entry?.strategy || 'unknown',
      metrics: { ...metrics },
      score,
    };
  });

  const ranking = enriched
    .slice()
    .sort((a, b) => b.score - a.score);

  const best = ranking[0] || null;
  const worst = ranking[ranking.length - 1] || null;
  const spread = ranking.length
    ? {
        min: ranking[ranking.length - 1].score,
        max: ranking[0].score,
        delta: ranking[0].score - ranking[ranking.length - 1].score,
      }
    : { min: 0, max: 0, delta: 0 };

  return {
    metric,
    ranking,
    leaders: { best, worst },
    spread,
  };
}

export function exportReport(summary, options = {}) {
  const { format = 'json', precision = 4 } = options;
  const payload = summary || {};

  if (format === 'json') {
    return JSON.stringify(payload, null, 2);
  }

  if (format === 'csv') {
    const rows = [];
    if (Array.isArray(payload.ranking)) {
      rows.push(['id', 'strategy', 'score'].join(','));
      payload.ranking.forEach((entry) => {
        rows.push([
          sanitizeReportValue(entry.id),
          sanitizeReportValue(entry.strategy),
          sanitizeReportValue(
            Number.isFinite(entry.score) ? entry.score.toFixed(precision) : '',
          ),
        ].join(','));
      });
    }
    return rows.join('\n');
  }

  if (format === 'markdown') {
    const lines = ['| Strategy | Score |', '| --- | --- |'];
    (payload.ranking || []).forEach((entry) => {
      const score = Number.isFinite(entry.score) ? entry.score.toFixed(precision) : 'n/a';
      lines.push(
        `| ${sanitizeReportValue(entry.strategy)} | ${sanitizeReportValue(score)} |`,
      );
    });
    return lines.join('\n');
  }

  throw new Error(`Unsupported export format: ${format}`);
}

export { renderDashboard, DASHBOARD_STYLES } from './dashboard_ui.js';
export { sanitizeReportValue, formatCurrency, formatPercent } from './formatters.js';
export { createRouter, Router } from '../router/index.js';
export { renderSignalsView } from '../views/signals.js';
export { renderOverviewView } from '../views/overview.js';
export { renderCommunityView } from '../views/community.js';
export { renderMonitoringView } from '../views/monitoring.js';

export class DashboardState {
  constructor({ strategies = [], backtests = [] } = {}) {
    this.configurator = createStrategyConfigurator(strategies);
    this.backtests = backtests.slice();
  }

  updateStrategy(name, updates) {
    return this.configurator.update(name, updates);
  }

  addBacktest(result) {
    if (!result) {
      throw new Error('Backtest result is required');
    }
    this.backtests.push(result);
    return this.backtests.length;
  }

  compare(metric = DEFAULT_METRIC) {
    return compareBacktests(this.backtests, metric);
  }

  export(format = 'json') {
    const comparison = this.compare();
    return exportReport(
      {
        strategies: this.configurator.list(),
        ranking: comparison.ranking,
        leaders: comparison.leaders,
        spread: comparison.spread,
        metric: comparison.metric,
      },
      { format },
    );
  }
}
