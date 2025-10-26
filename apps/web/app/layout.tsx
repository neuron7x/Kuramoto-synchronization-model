import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import './styles.css'
import { SiteHeader } from './components/site-header'

export const metadata: Metadata = {
  title: 'TradePulse Scenario Studio',
  description: 'Sanity-check strategy templates with guardrails before promoting them to production.',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="tp-body">
        <div className="tp-app">
          <SiteHeader />
          <div className="tp-content">{children}</div>
        </div>
      </body>
    </html>
  )
}
