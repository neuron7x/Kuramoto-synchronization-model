'use client'

import { useAuthStore } from '@/stores/auth-store'

interface PermissionGuardProps {
  children: React.ReactNode
  permission?: string
  role?: string
  fallback?: React.ReactNode
}

/**
 * Component-level permission guard
 * Conditionally renders children based on user permissions or roles
 */
export function PermissionGuard({
  children,
  permission,
  role,
  fallback = null,
}: PermissionGuardProps) {
  const { hasPermission, hasRole } = useAuthStore()

  if (permission && !hasPermission(permission)) {
    return <>{fallback}</>
  }

  if (role && !hasRole(role)) {
    return <>{fallback}</>
  }

  return <>{children}</>
}
