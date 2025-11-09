/**
 * State stores for orders, fills, and ticks
 */

export class Store {
  constructor(initialState = []) {
    this.state = initialState;
    this.subscribers = new Set();
  }

  /**
   * Get current state
   */
  getState() {
    return this.state;
  }

  /**
   * Set state and notify subscribers
   */
  setState(newState) {
    this.state = newState;
    this.notify();
  }

  /**
   * Update state with a function
   */
  updateState(updater) {
    if (typeof updater !== 'function') {
      throw new Error('Updater must be a function');
    }
    this.state = updater(this.state);
    this.notify();
  }

  /**
   * Subscribe to state changes
   */
  subscribe(subscriber) {
    if (typeof subscriber !== 'function') {
      throw new Error('Subscriber must be a function');
    }
    this.subscribers.add(subscriber);
    
    // Return unsubscribe function
    return () => {
      this.subscribers.delete(subscriber);
    };
  }

  /**
   * Notify all subscribers
   */
  notify() {
    this.subscribers.forEach((subscriber) => {
      try {
        subscriber(this.state);
      } catch (error) {
        console.error('Subscriber error:', error);
      }
    });
  }

  /**
   * Clear state
   */
  clear() {
    this.state = [];
    this.notify();
  }
}

/**
 * Orders store
 */
export class OrdersStore extends Store {
  addOrder(order) {
    this.updateState((state) => [...state, order]);
  }

  updateOrder(orderId, updates) {
    this.updateState((state) =>
      state.map((order) =>
        order.order_id === orderId ? { ...order, ...updates } : order
      )
    );
  }

  removeOrder(orderId) {
    this.updateState((state) =>
      state.filter((order) => order.order_id !== orderId)
    );
  }

  getOrder(orderId) {
    return this.state.find((order) => order.order_id === orderId);
  }
}

/**
 * Fills store
 */
export class FillsStore extends Store {
  addFill(fill) {
    this.updateState((state) => [...state, fill]);
  }

  getFillsForOrder(orderId) {
    return this.state.filter((fill) => fill.order_id === orderId);
  }
}

/**
 * Ticks store
 */
export class TicksStore extends Store {
  updateTick(symbol, tick) {
    this.updateState((state) => {
      const index = state.findIndex((t) => t.symbol === symbol);
      if (index >= 0) {
        const newState = [...state];
        newState[index] = tick;
        return newState;
      }
      return [...state, tick];
    });
  }

  getTick(symbol) {
    return this.state.find((tick) => tick.symbol === symbol);
  }
}

// Global store instances
export const ordersStore = new OrdersStore();
export const fillsStore = new FillsStore();
export const ticksStore = new TicksStore();
