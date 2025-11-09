/**
 * Business logic aggregators for orders, fills, positions, and backtests
 */

import { ensureFinite, ensureMs } from '../core/precision.js';

/**
 * Aggregate fills into positions by symbol
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function aggregatePositions(fills = [], _orders = [], ticks = []) {
  const positionsBySymbol = new Map();
  
  // Process fills
  fills.forEach((fill) => {
    const symbol = fill.symbol;
    if (!symbol) return;
    
    const position = positionsBySymbol.get(symbol) || {
      symbol,
      netQuantity: 0,
      totalCost: 0,
      fills: [],
      lastFillTimestamp: null,
    };
    
    const side = fill.metadata?.side || fill.side;
    const quantity = ensureFinite(fill.filled_qty, 0);
    const price = ensureFinite(fill.fill_price, 0);
    const timestamp = ensureMs(fill.timestamp);
    
    // Update net quantity based on side
    if (side === 'BUY') {
      position.netQuantity += quantity;
      position.totalCost += quantity * price;
    } else if (side === 'SELL') {
      position.netQuantity -= quantity;
      position.totalCost -= quantity * price;
    }
    
    position.fills.push(fill);
    
    if (timestamp && (!position.lastFillTimestamp || timestamp > position.lastFillTimestamp)) {
      position.lastFillTimestamp = timestamp;
    }
    
    positionsBySymbol.set(symbol, position);
  });
  
  // Enrich with current market prices from ticks
  const ticksBySymbol = new Map();
  ticks.forEach((tick) => {
    if (tick.symbol) {
      ticksBySymbol.set(tick.symbol, tick);
    }
  });
  
  // Calculate exposure and unrealized PnL
  const positions = Array.from(positionsBySymbol.values()).map((position) => {
    const tick = ticksBySymbol.get(position.symbol);
    const currentPrice = ensureFinite(tick?.last_price ?? tick?.mid, 0);
    const avgPrice = position.netQuantity !== 0 
      ? position.totalCost / position.netQuantity 
      : 0;
    
    return {
      ...position,
      avgPrice,
      currentPrice,
      exposure: position.netQuantity * currentPrice,
      unrealizedPnl: position.netQuantity * (currentPrice - avgPrice),
    };
  });
  
  return positions;
}

/**
 * Build order rows with fill progress
 */
export function buildOrderRows(orders = [], fills = []) {
  const fillsByOrderId = new Map();
  
  fills.forEach((fill) => {
    const orderId = fill.order_id;
    if (!orderId) return;
    
    const orderFills = fillsByOrderId.get(orderId) || [];
    orderFills.push(fill);
    fillsByOrderId.set(orderId, orderFills);
  });
  
  return orders.map((order) => {
    const orderFills = fillsByOrderId.get(order.order_id) || [];
    const totalFilled = orderFills.reduce(
      (sum, fill) => sum + ensureFinite(fill.filled_qty, 0),
      0
    );
    const quantity = ensureFinite(order.quantity, 0);
    const progress = quantity > 0 ? Math.min(1, totalFilled / quantity) : 0;
    const remaining = Math.max(0, quantity - totalFilled);
    
    return {
      ...order,
      fills: orderFills,
      totalFilled,
      progress,
      remaining,
      timestamp: ensureMs(order.timestamp),
    };
  });
}

/**
 * Aggregate backtest results and rank by metric
 */
export function aggregateBacktests(backtests = [], metric = 'sharpe') {
  const enriched = backtests.map((entry) => {
    const meta = entry?.metadata || {};
    const metrics = entry?.metrics || {};
    const score = ensureFinite(metrics[metric], Number.NEGATIVE_INFINITY);
    
    return {
      id: meta.id || entry?.id || meta.label || `backtest-${Math.random().toString(16).slice(2)}`,
      strategy: meta.strategy || entry?.strategy || 'unknown',
      metrics: { ...metrics },
      score,
    };
  });
  
  const ranking = enriched.slice().sort((a, b) => b.score - a.score);
  
  return {
    metric,
    ranking,
    best: ranking[0] || null,
    worst: ranking[ranking.length - 1] || null,
  };
}

/**
 * Normalize raw event to internal model
 */
export function normalizeEvent(rawEvent) {
  if (!rawEvent || typeof rawEvent !== 'object') {
    return null;
  }
  
  return {
    eventId: rawEvent.event_id || rawEvent.eventId,
    schemaVersion: rawEvent.schema_version || rawEvent.schemaVersion || '1',
    timestamp: ensureMs(rawEvent.timestamp),
    type: rawEvent.type || rawEvent.event_type,
    payload: rawEvent,
  };
}
