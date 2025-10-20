import {
  getCurrencyFormatter,
  getDateTimeFormatter,
  getLocalizationContext,
  getNumberFormatter,
  getPercentFormatter,
} from '../i18n/number_format.js';

const RISKY_LEADING_CHAR_PATTERN = /^[=+\-@]/;
const MARKDOWN_META_CHAR_PATTERN = /([\\`*_{}\[\]()#+!|>])/g;

function isLocalizationCandidate(value) {
  if (!value || typeof value !== 'object') {
    return false;
  }
  if (Array.isArray(value)) {
    return false;
  }
  return (
    'locale' in value ||
    'preferredLocales' in value ||
    'currencyOverride' in value ||
    'timezone' in value ||
    'assetCurrencyMap' in value ||
    ('formats' in value && 'currency' in value)
  );
}

function splitOptionsAndLocalization(optionsOrLocalization, localization) {
  let options = {};
  let resolvedLocalization = localization;
  if (resolvedLocalization === undefined && isLocalizationCandidate(optionsOrLocalization)) {
    resolvedLocalization = optionsOrLocalization;
  } else if (
    optionsOrLocalization &&
    typeof optionsOrLocalization === 'object' &&
    !Array.isArray(optionsOrLocalization)
  ) {
    options = optionsOrLocalization;
  }
  return { options, localization: resolvedLocalization };
}

function splitCurrencyArguments(arg, localization) {
  let currency = undefined;
  let options = {};
  let resolvedLocalization = localization;

  if (typeof arg === 'string') {
    currency = arg;
  } else if (isLocalizationCandidate(arg)) {
    resolvedLocalization = arg;
  } else if (arg && typeof arg === 'object' && !Array.isArray(arg)) {
    if (typeof arg.currency === 'string') {
      currency = arg.currency;
    }
    options = { ...arg };
    delete options.currency;
  }

  return { currency, options, localization: resolvedLocalization };
}

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

  return text.replace(MARKDOWN_META_CHAR_PATTERN, '\\$1');
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

export function formatCurrency(value, currencyOrOptions, localization) {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const { currency, options, localization: descriptor } = splitCurrencyArguments(
    currencyOrOptions,
    localization,
  );
  const context = getLocalizationContext(descriptor);
  const digits = { ...(options || {}) };
  const absValue = Math.abs(value);
  if (absValue >= 1000) {
    if (typeof digits.maximumFractionDigits === 'undefined') {
      digits.maximumFractionDigits = 0;
    }
    if (typeof digits.minimumFractionDigits === 'undefined') {
      digits.minimumFractionDigits = 0;
    }
  }
  const formatter = getCurrencyFormatter(context, currency, digits);
  return formatter.format(value);
}

export function formatPercent(value, optionsOrLocalization, localization) {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const { options, localization: descriptor } = splitOptionsAndLocalization(
    optionsOrLocalization,
    localization,
  );
  const context = getLocalizationContext(descriptor);
  const formatter = getPercentFormatter(context, options);
  return formatter.format(value);
}

export function formatNumber(value, optionsOrLocalization, localization) {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const { options, localization: descriptor } = splitOptionsAndLocalization(
    optionsOrLocalization,
    localization,
  );
  const context = getLocalizationContext(descriptor);
  const formatter = getNumberFormatter(context, options);
  return formatter.format(value);
}

export function formatTimestamp(timestamp, optionsOrLocalization, localization) {
  if (!Number.isFinite(timestamp)) {
    return '—';
  }
  const { options, localization: descriptor } = splitOptionsAndLocalization(
    optionsOrLocalization,
    localization,
  );
  const context = getLocalizationContext(descriptor);
  const formatter = getDateTimeFormatter(context, options);
  return formatter.format(new Date(timestamp));
}
