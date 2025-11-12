import { apiConfig } from '@/config/env'
import { logger } from '@/lib/utils/logger'

export interface ApiError {
  message: string
  status: number
  code?: string
  details?: unknown
}

export class ApiClientError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public details?: unknown
  ) {
    super(message)
    this.name = 'ApiClientError'
  }
}

interface RequestOptions extends RequestInit {
  timeout?: number
  retry?: number
  retryDelay?: number
}

/**
 * API Client for making requests to the TradePulse backend
 */
export class ApiClient {
  private baseUrl: string
  private defaultTimeout: number
  private defaultHeaders: HeadersInit

  constructor(baseUrl: string = apiConfig.baseUrl, timeout: number = apiConfig.timeout) {
    this.baseUrl = baseUrl
    this.defaultTimeout = timeout
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    }
  }

  /**
   * Make a GET request
   */
  async get<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' })
  }

  /**
   * Make a POST request
   */
  async post<T>(path: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  /**
   * Make a PUT request
   */
  async put<T>(path: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  /**
   * Make a PATCH request
   */
  async patch<T>(path: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  /**
   * Make a DELETE request
   */
  async delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: 'DELETE' })
  }

  /**
   * Make a generic request
   */
  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { timeout = this.defaultTimeout, retry = 0, retryDelay = 1000, ...fetchOptions } = options

    const url = this.buildUrl(path)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    // Merge headers
    const headers = new Headers(this.defaultHeaders)
    if (fetchOptions.headers) {
      Object.entries(fetchOptions.headers).forEach(([key, value]) => {
        if (typeof value === 'string') {
          headers.set(key, value)
        }
      })
    }

    // Add authentication token if available
    const token = this.getAuthToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }

    // Add correlation ID for tracing
    const correlationId = this.generateCorrelationId()
    headers.set('X-Correlation-ID', correlationId)

    try {
      logger.debug(`API Request: ${fetchOptions.method} ${url}`, { correlationId })

      const response = await fetch(url, {
        ...fetchOptions,
        headers,
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        await this.handleErrorResponse(response, correlationId)
      }

      const data = await response.json()
      logger.debug(`API Response: ${response.status}`, { correlationId, data })

      return data as T
    } catch (error) {
      clearTimeout(timeoutId)

      // Retry logic
      if (retry > 0 && this.shouldRetry(error)) {
        logger.warn(`Retrying request (${retry} attempts left)`, { correlationId, error })
        await this.sleep(retryDelay)
        return this.request<T>(path, { ...options, retry: retry - 1, retryDelay: retryDelay * 2 })
      }

      logger.error('API Request failed', error, { correlationId, url })
      throw this.handleError(error)
    }
  }

  private buildUrl(path: string): string {
    const cleanPath = path.startsWith('/') ? path : `/${path}`
    return `${this.baseUrl}${cleanPath}`
  }

  private getAuthToken(): string | null {
    // In a real implementation, this would get the token from cookies or storage
    // For now, we'll return null and implement this when we add authentication
    if (typeof window !== 'undefined') {
      return localStorage.getItem('auth_token')
    }
    return null
  }

  private generateCorrelationId(): string {
    return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
  }

  private async handleErrorResponse(response: Response, correlationId: string): Promise<never> {
    let errorData: ApiError
    try {
      errorData = await response.json()
    } catch {
      errorData = {
        message: response.statusText || 'Unknown error',
        status: response.status,
      }
    }

    logger.error('API Error Response', new Error(errorData.message), {
      correlationId,
      ...errorData,
    })

    throw new ApiClientError(errorData.message, response.status, errorData.code, errorData.details)
  }

  private handleError(error: unknown): Error {
    if (error instanceof ApiClientError) {
      return error
    }

    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        return new ApiClientError('Request timeout', 408)
      }
      return new ApiClientError(error.message, 0)
    }

    return new ApiClientError('Unknown error', 0)
  }

  private shouldRetry(error: unknown): boolean {
    if (error instanceof ApiClientError) {
      // Retry on 5xx errors and some 4xx errors
      return error.status >= 500 || error.status === 408 || error.status === 429
    }
    return false
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }
}

// Export singleton instance
export const apiClient = new ApiClient()
