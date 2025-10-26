'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import { clearAccessToken, readAccessToken, persistAccessToken } from './token-storage'

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

type AuthSession = {
  accessToken: string
  accessTokenExpiresAt: number
  refreshToken: string
  refreshTokenExpiresAt: number
}

type StoredAccessToken = {
  accessToken: string
  expiresAt: number
}

type AuthContextValue = {
  status: AuthStatus
  accessToken: string | null
  expiresAt: number | null
  signIn: (session: AuthSession) => Promise<void>
  signOut: () => Promise<void>
  refresh: () => Promise<void>
}

const PUBLIC_ROUTES = ['/signin']
const AUTH_BROADCAST_CHANNEL = 'tp.auth:channel'
const REFRESH_THRESHOLD_MS = 60_000

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

type BroadcastMessage =
  | { type: 'sign-in'; payload: StoredAccessToken }
  | { type: 'sign-out' }
  | { type: 'refresh'; payload: StoredAccessToken }

async function requestRefresh(): Promise<StoredAccessToken> {
  const response = await fetch('/api/auth/token', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new Error('Unable to refresh the access token')
  }

  const body = (await response.json()) as { accessToken: string; expiresAt: number }
  if (!body.accessToken || typeof body.expiresAt !== 'number') {
    throw new Error('Malformed response while refreshing the access token')
  }

  return { accessToken: body.accessToken, expiresAt: body.expiresAt }
}

async function setRefreshCookie(session: AuthSession): Promise<void> {
  const response = await fetch('/api/auth/session', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify({ refreshToken: session.refreshToken, expiresAt: session.refreshTokenExpiresAt }),
  })

  if (!response.ok) {
    throw new Error('Failed to persist the refresh token cookie')
  }
}

async function clearRefreshCookie(): Promise<void> {
  const response = await fetch('/api/auth/session', {
    method: 'DELETE',
    cache: 'no-store',
  })

  if (!response.ok) {
    throw new Error('Failed to clear the refresh token cookie')
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [expiresAt, setExpiresAt] = useState<number | null>(null)
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const broadcastRef = useRef<BroadcastChannel | null>(null)
  const refreshTimerRef = useRef<number | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof BroadcastChannel === 'undefined') {
      return
    }

    const broadcast = new BroadcastChannel(AUTH_BROADCAST_CHANNEL)
    broadcast.onmessage = (event: MessageEvent<BroadcastMessage>) => {
      const message = event.data
      if (!message) {
        return
      }

      if (message.type === 'sign-out') {
        setStatus('unauthenticated')
        setAccessToken(null)
        setExpiresAt(null)
      } else {
        setStatus('authenticated')
        setAccessToken(message.payload.accessToken)
        setExpiresAt(message.payload.expiresAt)
      }
    }
    broadcastRef.current = broadcast

    return () => {
      broadcast.close()
      broadcastRef.current = null
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      try {
        const stored = await readAccessToken()
        if (cancelled) {
          return
        }

        if (stored && stored.accessToken && stored.expiresAt > Date.now()) {
          setStatus('authenticated')
          setAccessToken(stored.accessToken)
          setExpiresAt(stored.expiresAt)
          return
        }

        const refreshed = await requestRefresh()
        if (cancelled) {
          return
        }

        await persistAccessToken(refreshed)
        setStatus('authenticated')
        setAccessToken(refreshed.accessToken)
        setExpiresAt(refreshed.expiresAt)
      } catch (error) {
        console.warn('No active session detected. User must sign in.', error)
        await clearAccessToken()
        if (!cancelled) {
          setStatus('unauthenticated')
          setAccessToken(null)
          setExpiresAt(null)
        }
      }
    }

    bootstrap()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (status === 'loading') {
      return
    }

    if (status === 'authenticated' && pathname && PUBLIC_ROUTES.includes(pathname)) {
      const redirectTarget = searchParams?.get('redirect') || '/'
      router.replace(redirectTarget)
    }

    if (status === 'unauthenticated' && pathname && !PUBLIC_ROUTES.includes(pathname)) {
      const params = new URLSearchParams(searchParams ?? undefined)
      params.set('redirect', pathname)
      router.replace(`/signin?${params.toString()}`)
    }
  }, [status, pathname, router, searchParams])

  useEffect(() => {
    if (refreshTimerRef.current !== null) {
      window.clearTimeout(refreshTimerRef.current)
      refreshTimerRef.current = null
    }

    if (status !== 'authenticated' || !expiresAt) {
      return
    }

    const delay = Math.max(expiresAt - Date.now() - REFRESH_THRESHOLD_MS, 0)
    refreshTimerRef.current = window.setTimeout(() => {
      void refresh()
    }, delay)

    return () => {
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = null
      }
    }
  }, [expiresAt, status])

  const refresh = useCallback(async () => {
    try {
      const updated = await requestRefresh()
      await persistAccessToken(updated)
      setStatus('authenticated')
      setAccessToken(updated.accessToken)
      setExpiresAt(updated.expiresAt)
      broadcastRef.current?.postMessage({ type: 'refresh', payload: updated })
    } catch (error) {
      console.error('Refresh failed. Clearing the session.', error)
      await clearAccessToken()
      setStatus('unauthenticated')
      setAccessToken(null)
      setExpiresAt(null)
      broadcastRef.current?.postMessage({ type: 'sign-out' })
    }
  }, [])

  const signIn = useCallback(
    async (session: AuthSession) => {
      await setRefreshCookie(session)
      const stored: StoredAccessToken = {
        accessToken: session.accessToken,
        expiresAt: session.accessTokenExpiresAt,
      }
      await persistAccessToken(stored)
      setStatus('authenticated')
      setAccessToken(stored.accessToken)
      setExpiresAt(stored.expiresAt)
      broadcastRef.current?.postMessage({ type: 'sign-in', payload: stored })
      const redirectTarget = searchParams?.get('redirect') || '/'
      router.replace(redirectTarget)
    },
    [router, searchParams],
  )

  const signOut = useCallback(async () => {
    await clearRefreshCookie()
    await clearAccessToken()
    setStatus('unauthenticated')
    setAccessToken(null)
    setExpiresAt(null)
    broadcastRef.current?.postMessage({ type: 'sign-out' })
    const params = new URLSearchParams(searchParams ?? undefined)
    if (pathname && !PUBLIC_ROUTES.includes(pathname)) {
      params.set('redirect', pathname)
    }
    const suffix = params.toString()
    router.replace(suffix ? `/signin?${suffix}` : '/signin')
  }, [pathname, router, searchParams])

  const value = useMemo<AuthContextValue>(
    () => ({ status, accessToken, expiresAt, signIn, signOut, refresh }),
    [accessToken, expiresAt, refresh, signIn, signOut, status],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

