import { escapeHtml, formatNumber, formatTimestamp } from '../core/formatters.js';

const DEFAULT_COLORS = [
  'rgba(56, 189, 248, 0.85)',
  'rgba(168, 85, 247, 0.85)',
  'rgba(34, 197, 94, 0.85)',
  'rgba(249, 115, 22, 0.85)',
  'rgba(239, 68, 68, 0.85)',
  'rgba(236, 72, 153, 0.85)',
];

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

function normaliseMultiSeries(seriesList = []) {
  if (!Array.isArray(seriesList) || seriesList.length === 0) {
    return {
      series: [],
      min: 0,
      max: 0,
      colors: [],
    };
  }

  const normalised = seriesList.map((seriesData, index) => {
    const { points, min, max } = normaliseSeries(seriesData.data || []);
    return {
      id: seriesData.id || `series-${index}`,
      name: seriesData.name || `Series ${index + 1}`,
      points,
      min,
      max,
      color: seriesData.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length],
      axis: seriesData.axis || 'left',
    };
  });

  const allValues = normalised.flatMap((s) => s.points.map((p) => p.value));
  let globalMin = Math.min(...allValues);
  let globalMax = Math.max(...allValues);

  if (globalMin === globalMax) {
    const padding = Math.abs(globalMin) * 0.01 || 1;
    globalMin -= padding;
    globalMax += padding;
  }

  return {
    series: normalised,
    min: globalMin,
    max: globalMax,
    colors: normalised.map((s) => s.color),
  };
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

function renderGrid(width, height, ySteps = 5) {
  const lines = [];
  for (let i = 0; i <= ySteps; i++) {
    const y = (height / ySteps) * i;
    lines.push(`<line x1="0" y1="${y.toFixed(2)}" x2="${width}" y2="${y.toFixed(2)}" stroke="rgba(148, 163, 184, 0.15)" stroke-width="1" />`);
  }
  return lines.join('');
}

function renderAxes(width, height, min, max, ySteps = 5) {
  const yLabels = [];
  for (let i = 0; i <= ySteps; i++) {
    const value = max - ((max - min) / ySteps) * i;
    const y = (height / ySteps) * i;
    yLabels.push(`<text x="-5" y="${y.toFixed(2)}" text-anchor="end" dominant-baseline="middle" class="tp-chart-axis__label">${formatNumber(value, { maximumFractionDigits: 2 })}</text>`);
  }
  
  return `
    <g class="tp-chart-axes">
      ${yLabels.join('')}
    </g>
  `;
}

function renderMultiSeriesLegend(seriesList) {
  const items = seriesList.map((series) => {
    return `
      <li class="tp-chart-legend__item tp-chart-legend__item--multi">
        <span class="tp-chart-legend__color" style="background-color: ${escapeHtml(series.color)}"></span>
        <span class="tp-chart-legend__name">${escapeHtml(series.name)}</span>
      </li>
    `;
  }).join('');

  return `<ul class="tp-chart-legend tp-chart-legend--multi">${items}</ul>`;
}

function renderEvents(events = [], width, height, timestamps = []) {
  if (!events || events.length === 0) {
    return '';
  }

  const markers = events.map((event) => {
    // Find closest timestamp index
    const timestampIndex = timestamps.findIndex((ts) => ts === event.timestamp);
    if (timestampIndex === -1) {
      return '';
    }

    const stepX = timestamps.length > 1 ? width / (timestamps.length - 1) : 0;
    const x = Math.min(width, Math.max(0, stepX * timestampIndex));
    const eventClass = event.type ? `tp-chart-event--${event.type}` : '';

    return `
      <g class="tp-chart-event ${eventClass}" data-event-type="${escapeHtml(event.type || '')}">
        <line x1="${x.toFixed(2)}" y1="0" x2="${x.toFixed(2)}" y2="${height}" stroke="${event.color || 'rgba(239, 68, 68, 0.6)'}" stroke-width="2" stroke-dasharray="4" />
        <text x="${x.toFixed(2)}" y="-5" text-anchor="middle" class="tp-chart-event__label">${escapeHtml(event.label || event.type || '')}</text>
      </g>
    `;
  }).join('');

  return markers;
}

export function renderAreaChart({ id = 'chart', width = 480, height = 240, series = [], showGrid = true, showAxes = true } = {}) {
  const { points, min, max } = normaliseSeries(series);
  const path = buildPath(points, width, height, min, max);
  const line = buildLine(points, width, height, min, max);

  const gradientId = `${id}-gradient`;
  const grid = showGrid ? renderGrid(width, height) : '';
  const axes = showAxes ? renderAxes(width, height, min, max) : '';
  
  const labels = points
    .map((point) => `<li class="tp-chart-legend__item"><span>${escapeHtml(point.label)}</span><strong>${escapeHtml(formatNumber(point.value, { maximumFractionDigits: 2 }))}</strong></li>`)
    .join('');

  const legend = labels
    ? `<ul class="tp-chart-legend">${labels}</ul>`
    : '<div class="tp-chart-empty">Chart data is not available.</div>';

  const svg = `
    <svg class="tp-area-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Area chart">
      <defs>
        <linearGradient id="${escapeHtml(gradientId)}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(56, 189, 248, 0.6)" />
          <stop offset="100%" stop-color="rgba(56, 189, 248, 0.05)" />
        </linearGradient>
      </defs>
      <g class="tp-chart-grid">${grid}</g>
      ${axes}
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

export function renderMultiSeriesChart({ 
  id = 'multi-chart', 
  width = 480, 
  height = 240, 
  seriesList = [],
  events = [],
  showGrid = true,
  showAxes = true,
  showLegend = true,
} = {}) {
  const { series, min, max } = normaliseMultiSeries(seriesList);
  
  if (series.length === 0) {
    return {
      html: '<div class="tp-chart-empty">No chart data available.</div>',
      series: [],
      min: 0,
      max: 0,
    };
  }

  const grid = showGrid ? renderGrid(width, height) : '';
  const axes = showAxes ? renderAxes(width, height, min, max) : '';
  const timestamps = series[0]?.points.map((p) => p.timestamp) || [];
  const eventMarkers = renderEvents(events, width, height, timestamps);

  // Render all series
  const seriesPaths = series.map((seriesData, index) => {
    const gradientId = `${id}-gradient-${index}`;
    const path = buildPath(seriesData.points, width, height, min, max);
    const line = buildLine(seriesData.points, width, height, min, max);
    const gradientColor = seriesData.color.replace('0.85)', '0.4)').replace('0.85', '0.4');
    const fadeColor = seriesData.color.replace('0.85)', '0.05)').replace('0.85', '0.05');

    return `
      <defs>
        <linearGradient id="${escapeHtml(gradientId)}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${gradientColor}" />
          <stop offset="100%" stop-color="${fadeColor}" />
        </linearGradient>
      </defs>
      <g fill="none" stroke-width="2" class="tp-chart-series" data-series="${escapeHtml(seriesData.id)}">
        <path d="${path}" fill="url(#${escapeHtml(gradientId)})" stroke="none"></path>
        <path d="${line}" stroke="${seriesData.color}" fill="none"></path>
      </g>
    `;
  }).join('');

  const legend = showLegend ? renderMultiSeriesLegend(series) : '';

  const svg = `
    <svg class="tp-area-chart tp-area-chart--multi" viewBox="0 0 ${width} ${height}" role="img" aria-label="Multi-series area chart">
      ${seriesPaths}
      <g class="tp-chart-grid">${grid}</g>
      ${axes}
      ${eventMarkers}
    </svg>
  `;

  return {
    html: `<div class="tp-area-chart__container tp-area-chart__container--multi">${svg}${legend}</div>`,
    series,
    min,
    max,
  };
}
