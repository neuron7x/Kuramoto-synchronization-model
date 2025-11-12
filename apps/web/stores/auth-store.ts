import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import type { AuthState, User, AuthTokens, LoginCredentials, RegisterData } from '@/types/auth'
import { authService } from '@/lib/auth/auth-service'
import { logger } from '@/lib/utils/logger'

interface AuthStore extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => Promise<void>
  refreshTokens: () => Promise<void>
  setUser: (user: User | null) => void
  setTokens: (tokens: AuthTokens | null) => void
  setError: (error: string | null) => void
  setLoading: (isLoading: boolean) => void
  hasPermission: (permission: string) => boolean
  hasRole: (role: string) => boolean
  initialize: () => Promise<void>
}

export const useAuthStore = create<AuthStore>()(
  devtools(
    persist(
      (set, get) => ({
        user: null,
        tokens: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,

        initialize: async () => {
          // Check if tokens exist and are valid
          if (authService.isAuthenticated() && !authService.isTokenExpired()) {
            try {
              set({ isLoading: true, error: null })
              const user = await authService.getCurrentUser()
              set({ user, isAuthenticated: true, isLoading: false })
            } catch (error) {
              logger.error('Failed to initialize auth', error)
              authService.clearTokens()
              set({ user: null, isAuthenticated: false, isLoading: false })
            }
          }
        },

        login: async (credentials) => {
          try {
            set({ isLoading: true, error: null })
            const { user, tokens } = await authService.login(credentials)
            set({
              user,
              tokens,
              isAuthenticated: true,
              isLoading: false,
              error: null,
            })
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Login failed'
            set({ error: errorMessage, isLoading: false })
            throw error
          }
        },

        register: async (data) => {
          try {
            set({ isLoading: true, error: null })
            const { user, tokens } = await authService.register(data)
            set({
              user,
              tokens,
              isAuthenticated: true,
              isLoading: false,
              error: null,
            })
          } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Registration failed'
            set({ error: errorMessage, isLoading: false })
            throw error
          }
        },

        logout: async () => {
          try {
            set({ isLoading: true })
            await authService.logout()
            set({
              user: null,
              tokens: null,
              isAuthenticated: false,
              isLoading: false,
              error: null,
            })
          } catch (error) {
            logger.error('Logout failed', error)
            // Clear state anyway
            set({
              user: null,
              tokens: null,
              isAuthenticated: false,
              isLoading: false,
              error: null,
            })
          }
        },

        refreshTokens: async () => {
          try {
            const tokens = await authService.refreshTokens()
            set({ tokens, error: null })
          } catch (error) {
            logger.error('Token refresh failed', error)
            set({
              user: null,
              tokens: null,
              isAuthenticated: false,
              error: 'Session expired',
            })
            throw error
          }
        },

        setUser: (user) => set({ user, isAuthenticated: !!user }),

        setTokens: (tokens) => set({ tokens }),

        setError: (error) => set({ error }),

        setLoading: (isLoading) => set({ isLoading }),

        hasPermission: (permission) => {
          const { user } = get()
          return user?.permissions?.includes(permission) ?? false
        },

        hasRole: (role) => {
          const { user } = get()
          return user?.roles?.includes(role) ?? false
        },
      }),
      {
        name: 'tradepulse-auth',
        partialize: (state) => ({
          // Only persist user data, not tokens (they're in localStorage via authService)
          user: state.user,
        }),
      }
    ),
    {
      name: 'AuthStore',
    }
  )
)
