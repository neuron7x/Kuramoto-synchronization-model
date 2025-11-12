'use client'

import { useAuthStore } from '@/stores/auth-store'

/**
 * Hook for accessing authentication state and methods
 */
export function useAuth() {
  const {
    user,
    isAuthenticated,
    isLoading,
    error,
    login,
    register,
    logout,
    refreshTokens,
    hasPermission,
    hasRole,
  } = useAuthStore()

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    login,
    register,
    logout,
    refreshTokens,
    hasPermission,
    hasRole,
  }
}
