export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit'
export type OrderStatus =
  | 'pending'
  | 'open'
  | 'filled'
  | 'partially_filled'
  | 'cancelled'
  | 'rejected'
export type TimeInForce = 'GTC' | 'IOC' | 'FOK'

export interface Order {
  id: string
  symbol: string
  side: OrderSide
  type: OrderType
  status: OrderStatus
  price: number
  quantity: number
  filledQuantity: number
  remainingQuantity: number
  averagePrice: number
  timeInForce: TimeInForce
  stopPrice?: number
  createdAt: string
  updatedAt: string
  fee: number
  feeAsset: string
}

export interface CreateOrderRequest {
  symbol: string
  side: OrderSide
  type: OrderType
  quantity: number
  price?: number
  stopPrice?: number
  timeInForce?: TimeInForce
}

export interface OrderHistoryFilter {
  symbol?: string
  side?: OrderSide
  type?: OrderType
  status?: OrderStatus
  startDate?: string
  endDate?: string
  page?: number
  limit?: number
}
