import { apiClient } from '@/lib/api/client'
import type { AuthTokens, LoginCredentials, RegisterData, User } from '@/types/auth'
import { logger } from '@/lib/utils/logger'

const TOKEN_KEY = 'auth_token'
const REFRESH_TOKEN_KEY = 'refresh_token'

/**
 * Authentication service for handling login, logout, and token management
 */
export class AuthService {
  /**
   * Login with email and password
   */
  async login(credentials: LoginCredentials): Promise<{ user: User; tokens: AuthTokens }> {
    try {
      const response = await apiClient.post<{ user: User; tokens: AuthTokens }>(
        '/auth/login',
        credentials
      )

      // Store tokens
      this.setTokens(response.tokens)

      logger.info('User logged in successfully', { userId: response.user.id })
      return response
    } catch (error) {
      logger.error('Login failed', error)
      throw error
    }
  }

  /**
   * Register a new user
   */
  async register(data: RegisterData): Promise<{ user: User; tokens: AuthTokens }> {
    try {
      const response = await apiClient.post<{ user: User; tokens: AuthTokens }>(
        '/auth/register',
        data
      )

      // Store tokens
      this.setTokens(response.tokens)

      logger.info('User registered successfully', { userId: response.user.id })
      return response
    } catch (error) {
      logger.error('Registration failed', error)
      throw error
    }
  }

  /**
   * Logout the current user
   */
  async logout(): Promise<void> {
    try {
      await apiClient.post('/auth/logout', {})
    } catch (error) {
      logger.error('Logout request failed', error)
      // Continue with local cleanup even if API call fails
    } finally {
      this.clearTokens()
      logger.info('User logged out')
    }
  }

  /**
   * Refresh access token using refresh token
   */
  async refreshTokens(): Promise<AuthTokens> {
    const refreshToken = this.getRefreshToken()
    if (!refreshToken) {
      throw new Error('No refresh token available')
    }

    try {
      const response = await apiClient.post<{ tokens: AuthTokens }>('/auth/refresh', {
        refreshToken,
      })

      this.setTokens(response.tokens)
      logger.info('Tokens refreshed successfully')

      return response.tokens
    } catch (error) {
      logger.error('Token refresh failed', error)
      this.clearTokens()
      throw error
    }
  }

  /**
   * Get current user profile
   */
  async getCurrentUser(): Promise<User> {
    try {
      const user = await apiClient.get<User>('/auth/me')
      logger.debug('Current user fetched', { userId: user.id })
      return user
    } catch (error) {
      logger.error('Failed to fetch current user', error)
      throw error
    }
  }

  /**
   * Get access token
   */
  getAccessToken(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(TOKEN_KEY)
  }

  /**
   * Get refresh token
   */
  getRefreshToken(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  }

  /**
   * Set tokens in storage
   */
  setTokens(tokens: AuthTokens): void {
    if (typeof window === 'undefined') return
    localStorage.setItem(TOKEN_KEY, tokens.accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refreshToken)
  }

  /**
   * Clear tokens from storage
   */
  clearTokens(): void {
    if (typeof window === 'undefined') return
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated(): boolean {
    return this.getAccessToken() !== null
  }

  /**
   * Check if token is expired
   */
  isTokenExpired(): boolean {
    const token = this.getAccessToken()
    if (!token) return true

    try {
      const parts = token.split('.')
      if (parts.length !== 3 || !parts[1]) {
        return true
      }
      const payload = JSON.parse(atob(parts[1]))
      const expirationTime = payload.exp * 1000 // Convert to milliseconds
      return Date.now() >= expirationTime
    } catch {
      return true
    }
  }

  /**
   * Setup automatic token refresh
   */
  setupTokenRefresh(onRefreshFailed: () => void): () => void {
    const interval = setInterval(
      async () => {
        if (this.isAuthenticated() && this.isTokenExpired()) {
          try {
            await this.refreshTokens()
          } catch (error) {
            logger.error('Automatic token refresh failed', error)
            onRefreshFailed()
          }
        }
      },
      5 * 60 * 1000
    ) // Check every 5 minutes

    return () => clearInterval(interval)
  }
}

// Export singleton instance
export const authService = new AuthService()
