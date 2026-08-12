'use client'

import dynamic from 'next/dynamic'

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

const ScenarioStudio = dynamic(
  () =>
    import('./scenario-studio').then((mod) => ({
      default: mod.ScenarioStudio,
    })),
  {
    ssr: false,
    loading: () => <ScenarioStudioFallback />,
  }
)

export default function ScenarioStudioLoader() {
  return <ScenarioStudio />
}
