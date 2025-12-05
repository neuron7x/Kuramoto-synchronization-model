import { escapeHtml, formatNumber, formatTimestamp } from '../core/formatters.js';

function normaliseSeries(series = []) {
  const points = series
    .filter((point) => Number.isFinite(point.value))
    .map((point) => ({
      timestamp: point.timestamp,
      value: point.value,
      label: point.label || formatTimestamp(point.timestamp),
    }));

  if (!points.length) {
    return {
      points: [],
      min: 0,
      max: 0,
    };
  }

  const values = points.map((point) => point.value);
  let min = Math.min(...values);
  let max = Math.max(...values);

  if (min === max) {
    const padding = Math.abs(min) * 0.01 || 1;
    min -= padding;
    max += padding;
  }

  return { points, min, max };
}

function buildPath(points, width, height, min, max) {
  if (!points.length) {
    return '';
  }
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const range = max - min;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  const path = points
    .map((point, index) => {
      const x = Math.min(width, Math.max(0, stepX * index));
      const yRatio = (point.value - min) / range;
      const y = height - yRatio * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
  return `${path} L${width.toFixed(2)},${height.toFixed(2)} L0,${height.toFixed(2)} Z`;
}

function buildLine(points, width, height, min, max) {
  if (!points.length) {
    return '';
  }
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const range = max - min;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  return points
    .map((point, index) => {
      const x = Math.min(width, Math.max(0, stepX * index));
      const yRatio = (point.value - min) / range;
      const y = height - yRatio * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

export function renderAreaChart({ id = 'chart', width = 480, height = 240, series = [] } = {}) {
  const { points, min, max } = normaliseSeries(series);
  const path = buildPath(points, width, height, min, max);
  const line = buildLine(points, width, height, min, max);

  const gradientId = `${id}-gradient`;
  const labels = points
    .map((point) => `<li class="tp-chart-legend__item"><span>${escapeHtml(point.label)}</span><strong>${escapeHtml(formatNumber(point.value, { maximumFractionDigits: 2 }))}</strong></li>`)
    .join('');

  const legend = labels
    ? `<ul class="tp-chart-legend" role="list" aria-label="Chart data points">${labels}</ul>`
    : '<div class="tp-chart-empty" role="status" aria-live="polite">Chart data is not available. Data will appear here once trading activity begins.</div>';

  const chartLabel = points.length
    ? `Area chart with ${points.length} data points. Values range from ${formatNumber(min, { maximumFractionDigits: 2 })} to ${formatNumber(max, { maximumFractionDigits: 2 })}.`
    : 'Area chart with no data points.';

  const svg = `
    <svg class="tp-area-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${chartLabel}">
      <defs>
        <linearGradient id="${escapeHtml(gradientId)}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(56, 189, 248, 0.6)" />
          <stop offset="100%" stop-color="rgba(56, 189, 248, 0.05)" />
        </linearGradient>
      </defs>
      <g fill="none" stroke-width="2">
        <path d="${path}" fill="url(#${escapeHtml(gradientId)})" stroke="none"></path>
        <path d="${line}" stroke="rgba(56, 189, 248, 0.85)" fill="none"></path>
      </g>
    </svg>
  `;

  return {
    html: `<div class="tp-area-chart__container">${svg}${legend}</div>`,
    points,
    min,
    max,
  };
}
