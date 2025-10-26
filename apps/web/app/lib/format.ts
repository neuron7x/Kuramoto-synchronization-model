const numberFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 4,
  minimumFractionDigits: 0,
})

const timestampFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'medium',
})

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  if (!Number.isFinite(value)) {
    if (Number.isNaN(value)) {
      return 'NaN'
    }
    if (value === Infinity) {
      return '∞'
    }
    if (value === -Infinity) {
      return '-∞'
    }
  }
  if (options) {
    return new Intl.NumberFormat('en-US', options).format(value)
  }
  return numberFormatter.format(value)
}

export function formatBoolean(value: boolean): string {
  return value ? 'true' : 'false'
}

export function formatTimestamp(value: string | number | Date): string {
  const date = value instanceof Date ? value : new Date(value)
  return timestampFormatter.format(date)
}

export function formatAny(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'number') {
    return formatNumber(value)
  }
  if (typeof value === 'boolean') {
    return formatBoolean(value)
  }
  if (value instanceof Date) {
    return formatTimestamp(value)
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}
