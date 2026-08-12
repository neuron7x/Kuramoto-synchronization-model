import type { ReactNode } from 'react'
import type { Metadata } from 'next'

import { AppHeader } from './_components/app-header'

export const metadata: Metadata = {
  title: {
    template: '%s | GeoSync',
    default: 'Dashboard',
  },
}

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <AppHeader />
      {children}
    </>
  )
}
