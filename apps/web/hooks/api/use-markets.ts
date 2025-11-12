import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import type { Market, OHLCV, OrderBook } from '@/types/market'

export const MARKETS_QUERY_KEY = 'markets'

/**
 * Fetch all markets
 */
export function useMarkets() {
  return useQuery({
    queryKey: [MARKETS_QUERY_KEY],
    queryFn: () => apiClient.get<Market[]>('/markets'),
    staleTime: 30 * 1000, // 30 seconds
  })
}

/**
 * Fetch a specific market
 */
export function useMarket(symbol: string) {
  return useQuery({
    queryKey: [MARKETS_QUERY_KEY, symbol],
    queryFn: () => apiClient.get<Market>(`/markets/${symbol}`),
    enabled: !!symbol,
    staleTime: 10 * 1000, // 10 seconds
  })
}

/**
 * Fetch OHLCV data for a market
 */
export function useOHLCV(symbol: string, interval: string = '1h', limit: number = 100) {
  return useQuery({
    queryKey: [MARKETS_QUERY_KEY, symbol, 'ohlcv', interval, limit],
    queryFn: () =>
      apiClient.get<OHLCV[]>(`/markets/${symbol}/ohlcv`, {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval, limit }),
      } as RequestInit),
    enabled: !!symbol,
    staleTime: 60 * 1000, // 1 minute
  })
}

/**
 * Fetch order book for a market
 */
export function useOrderBook(symbol: string, depth: number = 20) {
  return useQuery({
    queryKey: [MARKETS_QUERY_KEY, symbol, 'orderbook', depth],
    queryFn: () => apiClient.get<OrderBook>(`/markets/${symbol}/orderbook?depth=${depth}`),
    enabled: !!symbol,
    staleTime: 5 * 1000, // 5 seconds
    refetchInterval: 5 * 1000, // Auto-refetch every 5 seconds
  })
}

/**
 * Subscribe to market updates via WebSocket
 */
export function useMarketUpdates() {
  const queryClient = useQueryClient()

  const subscribeToMarket = useMutation({
    mutationFn: async (symbol: string) => {
      // WebSocket subscription logic would go here
      // For now, just return success
      return { symbol, subscribed: true }
    },
    onSuccess: () => {
      // Invalidate markets query to refetch
      queryClient.invalidateQueries({ queryKey: [MARKETS_QUERY_KEY] })
    },
  })

  return subscribeToMarket
}
