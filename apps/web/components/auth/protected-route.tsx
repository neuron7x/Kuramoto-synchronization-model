'use client'

import { useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuthStore } from '@/stores/auth-store'
import { logger } from '@/lib/utils/logger'

interface ProtectedRouteProps {
  children: React.ReactNode
  requiredPermission?: string
  requiredRole?: string
  redirectTo?: string
}

/**
 * Protected route wrapper that ensures user is authenticated
 * and optionally has specific permissions or roles
 */
export function ProtectedRoute({
  children,
  requiredPermission,
  requiredRole,
  redirectTo = '/signin',
}: ProtectedRouteProps) {
  const router = useRouter()
  const pathname = usePathname()
  const { isAuthenticated, isLoading, hasPermission, hasRole, initialize } = useAuthStore()

  useEffect(() => {
    initialize()
  }, [initialize])

  useEffect(() => {
    if (!isLoading) {
      if (!isAuthenticated) {
        logger.warn('Unauthenticated access attempt', { pathname })
        router.push(`${redirectTo}?redirect=${encodeURIComponent(pathname)}`)
        return
      }

      if (requiredPermission && !hasPermission(requiredPermission)) {
        logger.warn('Insufficient permissions', { pathname, requiredPermission })
        router.push('/403')
        return
      }

      if (requiredRole && !hasRole(requiredRole)) {
        logger.warn('Insufficient role', { pathname, requiredRole })
        router.push('/403')
        return
      }
    }
  }, [
    isAuthenticated,
    isLoading,
    requiredPermission,
    requiredRole,
    pathname,
    router,
    redirectTo,
    hasPermission,
    hasRole,
  ])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-brand-600 border-r-transparent" />
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null // Will redirect in useEffect
  }

  if (requiredPermission && !hasPermission(requiredPermission)) {
    return null // Will redirect in useEffect
  }

  if (requiredRole && !hasRole(requiredRole)) {
    return null // Will redirect in useEffect
  }

  return <>{children}</>
}
