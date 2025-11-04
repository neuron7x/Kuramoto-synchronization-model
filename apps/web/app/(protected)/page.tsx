import type { Metadata } from 'next'
import nextDynamic from 'next/dynamic'

const ScenarioStudio = nextDynamic(
  () =>
    import('./_components/scenario-studio').then((mod) => ({
      default: mod.ScenarioStudio,
    })),
  {
    ssr: false,
    loading: () => <ScenarioStudioFallback />,
  }
)

function ScenarioStudioFallback() {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: '2rem',
      }}
    >
      <div
        role="status"
        aria-live="polite"
        aria-busy="true"
        style={{
          width: 'min(320px, 90vw)',
          textAlign: 'center',
        }}
      >
        <progress
          aria-label="Loading Scenario Studio"
          style={{ width: '100%', height: '0.5rem' }}
        />
        <p
          style={{
            marginTop: '1rem',
            color: 'var(--mui-palette-text-secondary, #5f6368)',
            fontSize: '0.95rem',
          }}
        >
          Preparing the Scenario Studio…
        </p>
      </div>
    </div>
  )
}

export const metadata: Metadata = {
  title: 'Scenario Studio | TradePulse',
  description:
    'Optimise trading strategy templates with guardrails, validation and actionable risk insights before deployment.',
}

export const dynamic = 'force-static'
export const revalidate = 3600

export default function ProtectedHomePage() {
  return <ScenarioStudio />
}
