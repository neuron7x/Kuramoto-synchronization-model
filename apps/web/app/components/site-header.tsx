'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useMemo } from 'react'

const NAV_LINKS: Array<{ href: string; label: string }> = [
  { href: '/', label: 'Scenario Studio' },
  { href: '/health', label: 'Health' },
  { href: '/metrics', label: 'Metrics' },
  { href: '/streams', label: 'Realtime stream' },
]

function isActive(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/'
  }
  if (pathname === href) {
    return true
  }
  return pathname.startsWith(`${href}/`)
}

export function SiteHeader() {
  const pathname = usePathname() ?? '/'
  const activeMap = useMemo(() => {
    return NAV_LINKS.reduce<Record<string, boolean>>((acc, link) => {
      acc[link.href] = isActive(pathname, link.href)
      return acc
    }, {})
  }, [pathname])

  return (
    <header className="tp-top-bar">
      <div className="tp-top-bar__inner">
        <Link href="/" className="tp-brand" aria-label="TradePulse home">
          TradePulse
        </Link>
        <nav aria-label="Primary" className="tp-nav">
          {NAV_LINKS.map((link) => {
            const active = activeMap[link.href]
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`tp-nav__link${active ? ' tp-nav__link--active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                {link.label}
              </Link>
            )
          })}
        </nav>
      </div>
    </header>
  )
}
