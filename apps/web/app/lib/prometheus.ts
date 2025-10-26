export interface PrometheusSample {
  name: string
  labels: Record<string, string>
  value: number
  rawValue: string
  timestamp?: number
}

export interface MetricSummary {
  name: string
  count: number
  min: number | null
  max: number | null
  lastValue: number | null
  lastRawValue: string
}

const SAMPLE_REGEX =
  /^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(-?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][+-]?\d+)?|[+-]Inf|NaN)(?:\s+(-?\d+))?$/

const LABEL_REGEX = /([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^\\"])*)"/g

function parseLabels(raw: string | undefined): Record<string, string> {
  if (!raw) {
    return {}
  }
  const labels: Record<string, string> = {}
  const content = raw.slice(1, -1)
  let match: RegExpExecArray | null
  while ((match = LABEL_REGEX.exec(content)) !== null) {
    const key = match[1]
    const value = match[2].replace(/\\"/g, '"').replace(/\\n/g, '\n').replace(/\\t/g, '\t')
    labels[key] = value.replace(/\\\\/g, '\\')
  }
  return labels
}

function coerceValue(rawValue: string): number {
  if (rawValue === '+Inf' || rawValue === 'Inf') {
    return Infinity
  }
  if (rawValue === '-Inf') {
    return -Infinity
  }
  if (rawValue === 'NaN') {
    return Number.NaN
  }
  return Number(rawValue)
}

export function parsePrometheusText(payload: string): PrometheusSample[] {
  const samples: PrometheusSample[] = []
  const lines = payload.split(/\r?\n/)
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      continue
    }
    const match = trimmed.match(SAMPLE_REGEX)
    if (!match) {
      continue
    }
    const [, name, labelPart, rawValue, timestamp] = match
    samples.push({
      name,
      labels: parseLabels(labelPart),
      value: coerceValue(rawValue),
      rawValue,
      timestamp: timestamp ? Number(timestamp) : undefined,
    })
  }
  return samples
}

export function summariseSamples(samples: PrometheusSample[]): MetricSummary[] {
  const summaries = new Map<string, MetricSummary & { hasFinite: boolean }>()
  for (const sample of samples) {
    const existing = summaries.get(sample.name)
    const isFiniteValue = Number.isFinite(sample.value)
    if (!existing) {
      summaries.set(sample.name, {
        name: sample.name,
        count: 1,
        min: isFiniteValue ? sample.value : null,
        max: isFiniteValue ? sample.value : null,
        lastValue: isFiniteValue ? sample.value : null,
        lastRawValue: sample.rawValue,
        hasFinite: isFiniteValue,
      })
      continue
    }
    existing.count += 1
    existing.lastValue = isFiniteValue ? sample.value : null
    existing.lastRawValue = sample.rawValue
    if (isFiniteValue) {
      if (existing.hasFinite) {
        existing.min = existing.min === null ? sample.value : Math.min(existing.min, sample.value)
        existing.max = existing.max === null ? sample.value : Math.max(existing.max, sample.value)
      } else {
        existing.min = sample.value
        existing.max = sample.value
        existing.hasFinite = true
      }
    }
  }
  return Array.from(summaries.values())
    .map(({ hasFinite, ...summary }) => summary)
    .sort((a, b) => {
      if (b.count !== a.count) {
        return b.count - a.count
      }
      return a.name.localeCompare(b.name)
    })
}
