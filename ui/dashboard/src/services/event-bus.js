/**
 * Centralized event bus with reducers for state management
 */

export class EventBus {
  constructor() {
    this.listeners = new Map();
    this.reducers = new Map();
    this.eventQueue = [];
    this.isProcessing = false;
    this.batchTimeout = null;
    this.batchDelayMs = 100; // Default 100ms batching
  }

  /**
   * Register a reducer for a specific event type
   */
  registerReducer(eventType, reducer) {
    if (typeof reducer !== 'function') {
      throw new Error(`Reducer for ${eventType} must be a function`);
    }
    this.reducers.set(eventType, reducer);
  }

  /**
   * Subscribe to events
   */
  subscribe(eventType, listener) {
    if (typeof listener !== 'function') {
      throw new Error('Listener must be a function');
    }
    
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    
    this.listeners.get(eventType).add(listener);
    
    // Return unsubscribe function
    return () => {
      const listeners = this.listeners.get(eventType);
      if (listeners) {
        listeners.delete(listener);
      }
    };
  }

  /**
   * Process a single event
   */
  processEvent(event) {
    if (!event || typeof event !== 'object') {
      return;
    }
    
    const { type, payload } = event;
    
    // Apply reducer if registered
    const reducer = this.reducers.get(type);
    let processedPayload = payload;
    
    if (reducer) {
      try {
        processedPayload = reducer(payload);
      } catch (error) {
        console.error(`Reducer error for ${type}:`, error);
      }
    }
    
    // Notify listeners
    const listeners = this.listeners.get(type);
    if (listeners) {
      listeners.forEach((listener) => {
        try {
          listener({ type, payload: processedPayload, originalPayload: payload });
        } catch (error) {
          console.error(`Listener error for ${type}:`, error);
        }
      });
    }
  }

  /**
   * Queue event for batch processing
   */
  queueEvent(event) {
    this.eventQueue.push(event);
    
    // Clear existing timeout and schedule new batch
    if (this.batchTimeout) {
      clearTimeout(this.batchTimeout);
    }
    
    this.batchTimeout = setTimeout(() => {
      this.processBatch();
    }, this.batchDelayMs);
  }

  /**
   * Process batched events
   */
  processBatch() {
    if (this.isProcessing || this.eventQueue.length === 0) {
      return;
    }
    
    this.isProcessing = true;
    const batch = this.eventQueue.splice(0);
    
    batch.forEach((event) => {
      this.processEvent(event);
    });
    
    this.isProcessing = false;
  }

  /**
   * Emit event immediately (no batching)
   */
  emit(event) {
    this.processEvent(event);
  }

  /**
   * Clear all listeners and reducers
   */
  clear() {
    this.listeners.clear();
    this.reducers.clear();
    this.eventQueue = [];
    if (this.batchTimeout) {
      clearTimeout(this.batchTimeout);
      this.batchTimeout = null;
    }
  }
}

// Global event bus instance
export const globalEventBus = new EventBus();
