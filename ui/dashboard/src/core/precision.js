/**
 * Unified precision and formatting policy for numeric values
 */

export class PrecisionPolicy {
  constructor(defaults = {}) {
    this.currencyPrecision = defaults.currencyPrecision ?? 2;
    this.percentPrecision = defaults.percentPrecision ?? 2;
    this.metricPrecision = defaults.metricPrecision ?? 4;
    this.largeCurrencyThreshold = defaults.largeCurrencyThreshold ?? 10000;
  }

  /**
   * Round a number to specified precision
   */
  round(value, precision) {
    if (!Number.isFinite(value)) {
      return value;
    }
    const multiplier = Math.pow(10, precision);
    return Math.round(value * multiplier) / multiplier;
  }

  /**
   * Format currency with appropriate precision
   */
  formatCurrency(value, currency = 'USD') {
    if (!Number.isFinite(value)) {
      return '—';
    }
    const precision = Math.abs(value) >= this.largeCurrencyThreshold ? 0 : this.currencyPrecision;
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    }).format(value);
  }

  /**
   * Format percentage with appropriate precision
   */
  formatPercent(value) {
    if (!Number.isFinite(value)) {
      return '—';
    }
    const precision = Math.abs(value) < 0.1 ? this.percentPrecision : Math.max(1, this.percentPrecision - 1);
    return `${(value * 100).toFixed(precision)}%`;
  }

  /**
   * Format metric value
   */
  formatMetric(value, precision = this.metricPrecision) {
    if (!Number.isFinite(value)) {
      return 'n/a';
    }
    return value.toFixed(precision);
  }
}

// Default global precision policy
export const defaultPrecisionPolicy = new PrecisionPolicy();

/**
 * Ensure a timestamp value is in milliseconds
 * Handles both seconds and milliseconds timestamps
 */
export function ensureMs(timestamp) {
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  
  // If timestamp is in seconds (less than year 2100 in seconds)
  // Convert to milliseconds
  if (timestamp < 4102444800) {
    return timestamp * 1000;
  }
  
  return timestamp;
}

/**
 * Validate that a value is a finite number
 */
export function ensureFinite(value, fallback = 0) {
  return Number.isFinite(value) ? value : fallback;
}

/**
 * Normalize a numeric value with bounds checking
 */
export function normalizeNumber(value, { min = -Infinity, max = Infinity, fallback = 0 } = {}) {
  if (!Number.isFinite(value)) {
    return fallback;
  }
  return Math.max(min, Math.min(max, value));
}
