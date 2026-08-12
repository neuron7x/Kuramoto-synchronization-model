import type { Metadata } from 'next'

import Container from '@mui/material/Container'

import { EdgeProbeClient } from './edge-probe-client'

export const metadata: Metadata = {
  title: 'Edge-case probe | GeoSync',
  description:
    'IERD-Q7 edge-case harness: issues a real request to a public endpoint and renders every ' +
    'edge-case state (loading, cancelled, server_error, network_failure, timeout, …) through one ' +
    'auditable surface for route-interception coverage.',
  robots: { index: false, follow: false },
}

export const dynamic = 'force-dynamic'

export default function EdgeProbePage() {
  return (
    <Container maxWidth="sm" sx={{ py: { xs: 4, md: 6 } }}>
      <EdgeProbeClient />
    </Container>
  )
}
