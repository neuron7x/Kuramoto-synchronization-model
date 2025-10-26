import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import './styles.css'
import { AppRouterCacheProvider } from '@mui/material-nextjs/v14-appRouter'
import { AppThemeProvider } from './providers'

export const metadata: Metadata = {
  title: 'TradePulse Scenario Studio',
  description: 'Sanity-check strategy templates with guardrails before promoting them to production.',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppRouterCacheProvider>
          <AppThemeProvider>{children}</AppThemeProvider>
        </AppRouterCacheProvider>
      </body>
    </html>
  )
}
