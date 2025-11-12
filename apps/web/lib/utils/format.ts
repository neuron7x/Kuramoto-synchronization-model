import { format as dateFnsFormat } from 'date-fns'
import { env } from '@/config/env'

/**
 * Format a number as currency
 */
export function formatCurrency(
  value: number,
  currency: string = env.NEXT_PUBLIC_CURRENCY_FORMAT,
  locale: string = env.NEXT_PUBLIC_DEFAULT_LOCALE
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

/**
 * Format a number with precision
 */
export function formatNumber(
  value: number,
  precision: number = 2,
  locale: string = env.NEXT_PUBLIC_DEFAULT_LOCALE
): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(value)
}

/**
 * Format a percentage
 */
export function formatPercent(
  value: number,
  precision: number = 2,
  locale: string = env.NEXT_PUBLIC_DEFAULT_LOCALE
): string {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(value / 100)
}

/**
 * Format a date
 */
export function formatDate(
  date: Date | string | number,
  formatStr: string = 'yyyy-MM-dd HH:mm:ss'
): string {
  const dateObj = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date
  return dateFnsFormat(dateObj, formatStr)
}

/**
 * Format a price change with color indication
 */
export function formatPriceChange(
  value: number,
  showSign: boolean = true
): {
  formatted: string
  className: string
} {
  const formatted = `${showSign && value > 0 ? '+' : ''}${formatNumber(value, env.NEXT_PUBLIC_PRICE_PRECISION)}`
  const className = value > 0 ? 'price-up' : value < 0 ? 'price-down' : 'text-neutral'
  return { formatted, className }
}

/**
 * Format large numbers (K, M, B)
 */
export function formatCompactNumber(
  value: number,
  locale: string = env.NEXT_PUBLIC_DEFAULT_LOCALE
): string {
  return new Intl.NumberFormat(locale, {
    notation: 'compact',
    compactDisplay: 'short',
    maximumFractionDigits: 1,
  }).format(value)
}

/**
 * Format volume with appropriate units
 */
export function formatVolume(value: number): string {
  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`
  }
  return value.toFixed(2)
}
