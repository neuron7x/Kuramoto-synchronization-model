import { fetchHealth, ApiConfigError, ApiResponseError } from '../lib/api'
import { formatAny, formatTimestamp } from '../lib/format'

export const dynamic = 'force-dynamic'

type ComponentEntry = [string, Awaited<ReturnType<typeof fetchHealth>>['components'][string]]

function normaliseKey(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'component'
}

function renderStatusLabel(status: string): string {
  return status
    .split('-')
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ')
}

function ComponentCard({ name, component }: { name: string; component: ComponentEntry[1] }) {
  const metrics = Object.entries(component.metrics ?? {})
  return (
    <li className="health-component" data-testid={`component-${normaliseKey(name)}`}>
      <div className="health-component__header">
        <h3>{name}</h3>
        <span className={`status-pill status-pill--${component.status}`}>{renderStatusLabel(component.status)}</span>
      </div>
      {component.detail ? <p className="health-component__detail">{component.detail}</p> : null}
      {metrics.length > 0 ? (
        <dl className="health-component__metrics">
          {metrics.map(([metricKey, value]) => (
            <div key={metricKey} className="health-component__metric">
              <dt>{metricKey.replace(/_/g, ' ')}</dt>
              <dd>{formatAny(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </li>
  )
}

export default async function HealthPage() {
  let errorMessage: string | null = null
  let entries: ComponentEntry[] = []
  let overallStatus: string | null = null
  let timestampLabel: string | null = null

  try {
    const health = await fetchHealth()
    entries = Object.entries(health.components)
    overallStatus = health.status
    timestampLabel = formatTimestamp(health.timestamp)
  } catch (error) {
    if (error instanceof ApiConfigError || error instanceof ApiResponseError || error instanceof Error) {
      errorMessage = error.message
    } else {
      errorMessage = 'Unable to load health information.'
    }
  }

  return (
    <main className="tp-main">
      <div className="tp-main__container">
        <header className="tp-page-header">
          <h1 className="tp-page-title">Platform health</h1>
          <p className="tp-page-description">
            Live readiness snapshot fetched from the TradePulse backend readiness probe.
          </p>
        </header>

        {errorMessage ? (
          <section className="panel" role="alert" data-testid="health-error">
            <h2>Backend unavailable</h2>
            <p className="tp-error">{errorMessage}</p>
          </section>
        ) : (
          <section className="panel" data-testid="health-overview">
            <div className="health-overall">
              <div className="health-overall__status">
                <span className={`status-pill status-pill--overall-${overallStatus}`} data-testid="health-overall-status">
                  {overallStatus ? renderStatusLabel(overallStatus) : 'Unknown'}
                </span>
                {timestampLabel ? <span className="health-overall__timestamp">Updated {timestampLabel}</span> : null}
              </div>
              <p className="health-overall__hint">
                Track whether risk managers, caches, and analytics stores are ready for trading workloads.
              </p>
            </div>
            <ul className="health-components" data-testid="health-components">
              {entries.map(([name, component]) => (
                <ComponentCard key={name} name={name} component={component} />
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  )
}
