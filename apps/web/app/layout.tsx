import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { Suspense } from 'react'

import './styles.css'
import { AppRouterCacheProvider } from '@mui/material-nextjs/v14-appRouter'
import { AppThemeProvider } from './providers'
import { AuthProvider } from './auth/auth-provider'
import { WebVitalsReporter } from './_components/web-vitals-reporter'

export const metadata: Metadata = {
  title: 'GeoSync Scenario Studio',
  description:
    'Validate and stress-test quantitative strategy scenarios with institutional guardrails before promoting to live execution.',
}

function LoadingFallback() {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
      }}
    >
      <div role="status" aria-live="polite" aria-busy="true">
        Loading...
      </div>
    </div>
  )
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <WebVitalsReporter />
        <AppRouterCacheProvider>
          <AppThemeProvider>
            <Suspense fallback={<LoadingFallback />}>
              <AuthProvider>{children}</AuthProvider>
            </Suspense>
          </AppThemeProvider>
        </AppRouterCacheProvider>
      </body>
    </html>
  )
}
