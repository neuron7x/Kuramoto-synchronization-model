import { useQuery, useMutation, useQueryClient, UseQueryOptions } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import type { Order, CreateOrderRequest, OrderHistoryFilter } from '@/types/order'
import { logger } from '@/lib/utils/logger'

export const ORDERS_QUERY_KEY = 'orders'

/**
 * Fetch active orders
 */
export function useActiveOrders(symbol?: string) {
  return useQuery({
    queryKey: [ORDERS_QUERY_KEY, 'active', symbol],
    queryFn: () => apiClient.get<Order[]>(`/orders/active${symbol ? `?symbol=${symbol}` : ''}`),
    staleTime: 5 * 1000, // 5 seconds
    refetchInterval: 10 * 1000, // Auto-refetch every 10 seconds
  })
}

/**
 * Fetch order history
 */
export function useOrderHistory(filter?: OrderHistoryFilter) {
  const queryParams = new URLSearchParams()
  if (filter) {
    Object.entries(filter).forEach(([key, value]) => {
      if (value !== undefined) {
        queryParams.append(key, String(value))
      }
    })
  }

  return useQuery({
    queryKey: [ORDERS_QUERY_KEY, 'history', filter],
    queryFn: () =>
      apiClient.get<{ orders: Order[]; total: number }>(
        `/orders/history?${queryParams.toString()}`
      ),
    staleTime: 30 * 1000, // 30 seconds
  })
}

/**
 * Fetch a specific order
 */
export function useOrder(
  orderId: string,
  options?: Omit<UseQueryOptions<Order>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [ORDERS_QUERY_KEY, orderId],
    queryFn: () => apiClient.get<Order>(`/orders/${orderId}`),
    enabled: !!orderId,
    ...options,
  })
}

/**
 * Create a new order
 */
export function useCreateOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (orderData: CreateOrderRequest) => {
      logger.info('Creating order', {
        symbol: orderData.symbol,
        side: orderData.side,
        type: orderData.type,
      })
      return apiClient.post<Order>('/orders', orderData)
    },
    onSuccess: (order) => {
      logger.info('Order created successfully', { orderId: order.id })
      // Invalidate active orders query
      queryClient.invalidateQueries({ queryKey: [ORDERS_QUERY_KEY, 'active'] })
      // Invalidate order history
      queryClient.invalidateQueries({ queryKey: [ORDERS_QUERY_KEY, 'history'] })
    },
    onError: (error) => {
      logger.error('Failed to create order', error)
    },
  })
}

/**
 * Cancel an order
 */
export function useCancelOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (orderId: string) => {
      logger.info('Cancelling order', { orderId })
      return apiClient.delete<Order>(`/orders/${orderId}`)
    },
    onSuccess: (order) => {
      logger.info('Order cancelled successfully', { orderId: order.id })
      // Invalidate active orders
      queryClient.invalidateQueries({ queryKey: [ORDERS_QUERY_KEY, 'active'] })
      // Update the specific order in cache
      queryClient.invalidateQueries({ queryKey: [ORDERS_QUERY_KEY, order.id] })
      // Invalidate order history
      queryClient.invalidateQueries({ queryKey: [ORDERS_QUERY_KEY, 'history'] })
    },
    onError: (error) => {
      logger.error('Failed to cancel order', error)
    },
  })
}

/**
 * Cancel all orders for a symbol
 */
export function useCancelAllOrders() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (symbol?: string) => {
      logger.info('Cancelling all orders', { symbol })
      return apiClient.delete<{ cancelled: number }>(
        `/orders/all${symbol ? `?symbol=${symbol}` : ''}`
      )
    },
    onSuccess: (result, symbol) => {
      logger.info('All orders cancelled', { count: result.cancelled })
      // Invalidate all order-related queries
      queryClient.invalidateQueries({ queryKey: [ORDERS_QUERY_KEY] })
    },
    onError: (error) => {
      logger.error('Failed to cancel all orders', error)
    },
  })
}
