import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { Suspense } from 'react'

import './styles.css'
import { AppRouterCacheProvider } from '@mui/material-nextjs/v14-appRouter'
import { AppThemeProvider } from './providers'
import { AuthProvider } from './auth/auth-provider'

export const metadata: Metadata = {
  title: 'TradePulse Scenario Studio',
  description:
    'Sanity-check strategy templates with guardrails before promoting them to production.',
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
