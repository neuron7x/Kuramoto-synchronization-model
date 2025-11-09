/**
 * Selectors for deriving state from stores
 */

import { aggregatePositions, aggregateBacktests } from '../domain/aggregators.js';
import { ordersStore, fillsStore, ticksStore } from './stores.js';

/**
 * Memoization helper
 */
class Memoizer {
  constructor() {
    this.cache = new Map();
  }

  memoize(key, fn) {
    if (this.cache.has(key)) {
      return this.cache.get(key);
    }
    const result = fn();
    this.cache.set(key, result);
    return result;
  }

  clear() {
    this.cache.clear();
  }

  invalidate(key) {
    this.cache.delete(key);
  }
}

const memoizer = new Memoizer();

/**
 * Select positions from fills, orders, and ticks
 */
export function positionsSelector() {
  const fills = fillsStore.getState();
  const orders = ordersStore.getState();
  const ticks = ticksStore.getState();
  
  // Create cache key based on array lengths and timestamps
  const cacheKey = `positions:${fills.length}:${orders.length}:${ticks.length}`;
  
  return memoizer.memoize(cacheKey, () => {
    return aggregatePositions(fills, orders, ticks);
  });
}

/**
 * Select backtest results
 */
export function backtestsSelector(backtests, metric = 'sharpe') {
  const cacheKey = `backtests:${backtests.length}:${metric}`;
  
  return memoizer.memoize(cacheKey, () => {
    return aggregateBacktests(backtests, metric);
  });
}

/**
 * Select orders with fill progress
 */
export function ordersWithProgressSelector() {
  const orders = ordersStore.getState();
  const fills = fillsStore.getState();
  
  const cacheKey = `orders-progress:${orders.length}:${fills.length}`;
  
  return memoizer.memoize(cacheKey, () => {
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
        (sum, fill) => sum + (fill.filled_qty || 0),
        0
      );
      const quantity = order.quantity || 0;
      const progress = quantity > 0 ? Math.min(1, totalFilled / quantity) : 0;
      
      return {
        ...order,
        fills: orderFills,
        totalFilled,
        progress,
        remaining: Math.max(0, quantity - totalFilled),
      };
    });
  });
}

/**
 * Clear all selector caches
 */
export function clearSelectorCache() {
  memoizer.clear();
}

/**
 * Invalidate specific selector cache
 */
export function invalidateSelectorCache(key) {
  memoizer.invalidate(key);
}
