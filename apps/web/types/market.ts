export interface Market {
  id: string
  symbol: string
  name: string
  baseAsset: string
  quoteAsset: string
  lastPrice: number
  priceChange24h: number
  priceChangePercent24h: number
  volume24h: number
  high24h: number
  low24h: number
  bidPrice: number
  askPrice: number
  spread: number
  status: 'active' | 'paused' | 'delisted'
  minOrderSize: number
  maxOrderSize: number
  priceStep: number
  quantityStep: number
}

export interface OHLCV {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface OrderBookLevel {
  price: number
  quantity: number
  total: number
}

export interface OrderBook {
  symbol: string
  bids: OrderBookLevel[]
  asks: OrderBookLevel[]
  lastUpdate: number
}

export interface Ticker {
  symbol: string
  price: number
  change: number
  changePercent: number
  volume: number
  timestamp: number
}
