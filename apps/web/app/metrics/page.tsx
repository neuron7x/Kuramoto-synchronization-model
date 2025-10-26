import { ApiConfigError, ApiResponseError, fetchMetrics } from '../lib/api'
import { formatNumber } from '../lib/format'
import { parsePrometheusText, summariseSamples } from '../lib/prometheus'

export const dynamic = 'force-dynamic'

function renderValue(value: number | null, fallback: string): string {
  if (value === null || Number.isNaN(value)) {
    return fallback
  }
  return formatNumber(value)
}

export default async function MetricsPage() {
  let errorMessage: string | null = null
  let metricsPayload = ''
  let summaries: ReturnType<typeof summariseSamples> = []

  try {
    metricsPayload = await fetchMetrics()
    const samples = parsePrometheusText(metricsPayload)
    summaries = summariseSamples(samples).slice(0, 8)
  } catch (error) {
    if (error instanceof ApiConfigError || error instanceof ApiResponseError || error instanceof Error) {
      errorMessage = error.message
    } else {
      errorMessage = 'Unable to load metrics payload.'
    }
  }

  return (
    <main className="tp-main">
      <div className="tp-main__container">
        <header className="tp-page-header">
          <h1 className="tp-page-title">Metrics export</h1>
          <p className="tp-page-description">
            Inspect live Prometheus samples to confirm the inference API is exposing operational telemetry.
          </p>
        </header>

        {errorMessage ? (
          <section className="panel" role="alert" data-testid="metrics-error">
            <h2>Metrics unavailable</h2>
            <p className="tp-error">{errorMessage}</p>
          </section>
        ) : (
          <>
            <section className="panel" data-testid="metrics-overview">
              <h2>Key metric families</h2>
              <p className="tp-helper">
                Overview of the most active metric series. Track count and value envelopes to validate scraping pipelines.
              </p>
              <ul className="metrics-summary__list">
                {summaries.map((summary) => (
                  <li key={summary.name} className="metrics-summary__item" data-testid={`metric-${summary.name}`}>
                    <h3 className="metrics-summary__title">{summary.name}</h3>
                    <div className="metrics-summary__grid">
                      <div>
                        <span className="metrics-summary__label">Series count</span>
                        <span className="metrics-summary__value">{formatNumber(summary.count, { maximumFractionDigits: 0 })}</span>
                      </div>
                      <div>
                        <span className="metrics-summary__label">Minimum</span>
                        <span className="metrics-summary__value">{renderValue(summary.min, '—')}</span>
                      </div>
                      <div>
                        <span className="metrics-summary__label">Maximum</span>
                        <span className="metrics-summary__value">{renderValue(summary.max, '—')}</span>
                      </div>
                      <div>
                        <span className="metrics-summary__label">Last sample</span>
                        <span className="metrics-summary__value">
                          {summary.lastValue !== null ? renderValue(summary.lastValue, summary.lastRawValue) : summary.lastRawValue}
                        </span>
                      </div>
                    </div>
                  </li>
                ))}
                {summaries.length === 0 ? (
                  <li className="metrics-summary__empty">No numeric samples returned.</li>
                ) : null}
              </ul>
            </section>

            <section className="panel" data-testid="metrics-raw">
              <h2>Prometheus payload</h2>
              <p className="tp-helper tp-helper-spaced">
                Raw text response from <code>/metrics</code>. Use this to validate scrape targets or debug missing time-series.
              </p>
              <pre className="code-preview metrics-raw__content">{metricsPayload}</pre>
            </section>
          </>
        )}
      </div>
    </main>
  )
}
