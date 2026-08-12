import type { Metadata } from 'next'
import ScenarioStudioLoader from './_components/scenario-studio-loader'

export const metadata: Metadata = {
  title: 'Scenario Studio | GeoSync',
  description:
    'Optimise trading strategy templates with guardrails, validation and actionable risk insights before deployment.',
}

export const dynamic = 'force-static'
export const revalidate = 3600

export default function ProtectedHomePage() {
  return <ScenarioStudioLoader />
}
