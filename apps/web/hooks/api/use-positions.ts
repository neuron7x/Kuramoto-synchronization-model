import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import type { Position, PositionSummary, ClosedPosition } from '@/types/position'
import { logger } from '@/lib/utils/logger'

export const POSITIONS_QUERY_KEY = 'positions'

/**
 * Fetch all open positions
 */
export function usePositions() {
  return useQuery({
    queryKey: [POSITIONS_QUERY_KEY, 'open'],
    queryFn: () => apiClient.get<Position[]>('/positions'),
    staleTime: 5 * 1000, // 5 seconds
    refetchInterval: 10 * 1000, // Auto-refetch every 10 seconds
  })
}

/**
 * Fetch a specific position
 */
export function usePosition(symbol: string) {
  return useQuery({
    queryKey: [POSITIONS_QUERY_KEY, symbol],
    queryFn: () => apiClient.get<Position>(`/positions/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 1000, // 5 seconds
  })
}

/**
 * Fetch position summary
 */
export function usePositionSummary() {
  return useQuery({
    queryKey: [POSITIONS_QUERY_KEY, 'summary'],
    queryFn: () => apiClient.get<PositionSummary>('/positions/summary'),
    staleTime: 5 * 1000, // 5 seconds
    refetchInterval: 10 * 1000, // Auto-refetch every 10 seconds
  })
}

/**
 * Fetch closed positions history
 */
export function useClosedPositions(page: number = 1, limit: number = 20) {
  return useQuery({
    queryKey: [POSITIONS_QUERY_KEY, 'closed', page, limit],
    queryFn: () =>
      apiClient.get<{ positions: ClosedPosition[]; total: number }>(
        `/positions/closed?page=${page}&limit=${limit}`
      ),
    staleTime: 60 * 1000, // 1 minute
  })
}

/**
 * Close a position
 */
export function useClosePosition() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ symbol, quantity }: { symbol: string; quantity?: number }) => {
      logger.info('Closing position', { symbol, quantity })
      return apiClient.post<Position>(`/positions/${symbol}/close`, { quantity })
    },
    onSuccess: (position) => {
      logger.info('Position closed successfully', { symbol: position.symbol })
      // Invalidate positions queries
      queryClient.invalidateQueries({ queryKey: [POSITIONS_QUERY_KEY] })
    },
    onError: (error) => {
      logger.error('Failed to close position', error)
    },
  })
}

/**
 * Update position leverage
 */
export function useUpdateLeverage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ symbol, leverage }: { symbol: string; leverage: number }) => {
      logger.info('Updating leverage', { symbol, leverage })
      return apiClient.post<Position>(`/positions/${symbol}/leverage`, { leverage })
    },
    onSuccess: (position) => {
      logger.info('Leverage updated successfully', {
        symbol: position.symbol,
        leverage: position.leverage,
      })
      // Invalidate specific position
      queryClient.invalidateQueries({ queryKey: [POSITIONS_QUERY_KEY, position.symbol] })
      // Invalidate all positions
      queryClient.invalidateQueries({ queryKey: [POSITIONS_QUERY_KEY, 'open'] })
    },
    onError: (error) => {
      logger.error('Failed to update leverage', error)
    },
  })
}

/**
 * Update stop loss / take profit for a position
 */
export function useUpdatePositionLimits() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      symbol,
      stopLoss,
      takeProfit,
    }: {
      symbol: string
      stopLoss?: number
      takeProfit?: number
    }) => {
      logger.info('Updating position limits', { symbol, stopLoss, takeProfit })
      return apiClient.post<Position>(`/positions/${symbol}/limits`, { stopLoss, takeProfit })
    },
    onSuccess: (position) => {
      logger.info('Position limits updated', { symbol: position.symbol })
      queryClient.invalidateQueries({ queryKey: [POSITIONS_QUERY_KEY, position.symbol] })
      queryClient.invalidateQueries({ queryKey: [POSITIONS_QUERY_KEY, 'open'] })
    },
    onError: (error) => {
      logger.error('Failed to update position limits', error)
    },
  })
}
