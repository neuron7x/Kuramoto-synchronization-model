import { QueryClient, DefaultOptions } from '@tanstack/react-query'
import { logger } from './utils/logger'

const defaultOptions: DefaultOptions = {
  queries: {
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (formerly cacheTime)
    retry: (failureCount, error: unknown) => {
      // Don't retry on 4xx errors
      if (error && typeof error === 'object' && 'status' in error) {
        const status = (error as { status: number }).status
        if (status >= 400 && status < 500) {
          return false
        }
      }
      return failureCount < 3
    },
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    refetchOnMount: true,
  },
  mutations: {
    retry: false,
    onError: (error) => {
      logger.error('Mutation error', error instanceof Error ? error : new Error(String(error)))
    },
  },
}

/**
 * Create a new QueryClient instance
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions,
  })
}

// Singleton instance for use in app
export const queryClient = createQueryClient()
