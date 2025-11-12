export interface Position {
  id: string
  symbol: string
  side: 'long' | 'short'
  quantity: number
  entryPrice: number
  currentPrice: number
  markPrice: number
  liquidationPrice?: number
  unrealizedPnl: number
  unrealizedPnlPercent: number
  realizedPnl: number
  margin: number
  leverage: number
  openedAt: string
  updatedAt: string
}

export interface PositionSummary {
  totalPositions: number
  totalUnrealizedPnl: number
  totalRealizedPnl: number
  totalMargin: number
  accountBalance: number
  availableBalance: number
  marginLevel: number
}

export interface ClosedPosition {
  id: string
  symbol: string
  side: 'long' | 'short'
  quantity: number
  entryPrice: number
  exitPrice: number
  realizedPnl: number
  realizedPnlPercent: number
  fee: number
  openedAt: string
  closedAt: string
  duration: number
}
