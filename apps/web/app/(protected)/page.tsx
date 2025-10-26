import type { Metadata } from 'next'

import { ScenarioStudio } from './_components/scenario-studio'

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

