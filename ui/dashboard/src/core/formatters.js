const RISKY_LEADING_CHAR_PATTERN = /^[=+\-@]/;
const MARKDOWN_META_CHAR_PATTERN = new RegExp(
  String.raw`[\\\`*_{}\[\]()#+!|>]`,
  'g',
);

export function sanitizeReportValue(value) {
  if (value === null || value === undefined) {
    return '';
  }

  let text = String(value);

  if (RISKY_LEADING_CHAR_PATTERN.test(text)) {
    text = `'${text}`;
  }

  if (text.length === 0) {
    return text;
  }

  return text.replace(MARKDOWN_META_CHAR_PATTERN, (match) => `\\${match}`);
}

export function escapeHtml(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).replace(/[&<>"']/g, (char) => {
    switch (char) {
      case '&':
        return '&amp;';
      case '<':
        return '&lt;';
      case '>':
        return '&gt;';
      case '"':
        return '&quot;';
      case "'":
        return '&#39;';
      default:
        return char;
    }
  });
}

export function formatCurrency(value, currency = 'USD') {
  if (!Number.isFinite(value)) {
    return '—';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2,
  }).format(value);
}

export function formatPercent(value) {
  if (!Number.isFinite(value)) {
    return '—';
  }
  return `${(value * 100).toFixed(Math.abs(value) < 0.1 ? 2 : 1)}%`;
}

export function formatNumber(value, options = {}) {
  const { minimumFractionDigits = 0, maximumFractionDigits = 2 } = options;
  if (!Number.isFinite(value)) {
    return '—';
  }
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value);
}

export function formatTimestamp(timestamp) {
  if (!Number.isFinite(timestamp)) {
    return '—';
  }
  const date = new Date(timestamp);
  return date.toISOString().replace('T', ' ').replace('Z', ' UTC');
}

export function serializeForScript(value) {
  const json = JSON.stringify(value ?? {});
  return json
    .replace(/</g, '\\u003C')
    .replace(/>/g, '\\u003E')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}
