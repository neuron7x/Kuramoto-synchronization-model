# ADR 001: Event-Driven State Management

## Status
Accepted

## Context
The TradePulse Dashboard needs to manage real-time state from multiple sources (WebSocket events, API responses, user interactions) with the following requirements:

1. **Real-time updates**: Handle high-frequency market data ticks (potentially 100s per second)
2. **Consistency**: Ensure derived state (positions, aggregations) stays consistent with source data
3. **Performance**: Minimize re-renders and expensive computations
4. **Testability**: Easy to test business logic in isolation
5. **Maintainability**: Clear separation between state logic and UI

Previous implementation mixed state management with UI rendering, making it difficult to:
- Test business logic independently
- Optimize performance
- Track state changes
- Debug issues

## Decision
We will implement an event-driven architecture with the following components:

### 1. Event Bus (`services/event-bus.js`)
- Centralized event processing with pub/sub pattern
- Reducer support for event transformation
- Event batching (100ms coalescing) for performance
- Type-safe event routing

### 2. Stores (`services/stores.js`)
- Simple, mutable stores for each data type (orders, fills, ticks)
- Observable pattern with subscribe/notify
- Granular updates to minimize re-renders
- No complex state transitions (keep it simple)

### 3. Selectors (`services/selectors.js`)
- Pure functions that derive state from stores
- Memoization for performance
- Composition of multiple stores
- Cache invalidation based on input changes

### 4. Domain Layer (`domain/aggregators.js`)
- Business logic separated from state management
- Pure functions for aggregations
- Testable in isolation
- No side effects

## Alternatives Considered

### A. Redux
**Pros:**
- Well-established pattern
- Excellent dev tools
- Time-travel debugging

**Cons:**
- Heavyweight for our needs
- Boilerplate overhead
- Learning curve for team
- Overkill for a single-page dashboard

### B. MobX
**Pros:**
- Reactive updates
- Less boilerplate than Redux
- Good performance

**Cons:**
- Magic behavior (proxies)
- Harder to debug
- Additional dependency
- Not as simple as needed

### C. React State (Hooks)
**Pros:**
- No additional dependencies
- Standard React pattern
- Simple to understand

**Cons:**
- We're not using React
- Tight coupling with UI
- Hard to test business logic
- No built-in memoization

### D. Custom Event Bus (Selected)
**Pros:**
- Lightweight (no dependencies)
- Framework-agnostic
- Easy to understand and debug
- Optimized for our use case
- Full control over performance

**Cons:**
- Custom code to maintain
- No dev tools integration
- Need to implement batching ourselves

## Consequences

### Positive
1. **Performance**: Event batching reduces update frequency from 100s/sec to 10/sec
2. **Testability**: Business logic can be tested without UI
3. **Debugging**: Event flow is explicit and traceable
4. **Flexibility**: Easy to add new event types or stores
5. **Size**: No external dependencies (~3KB of custom code vs ~40KB for Redux)

### Negative
1. **Custom Code**: Need to maintain event bus implementation
2. **No Dev Tools**: Can't use Redux DevTools for time-travel debugging
3. **Documentation**: Need to document our custom patterns
4. **Learning**: Team needs to learn our specific approach

### Neutral
1. **Migration Path**: Can migrate to Redux/MobX later if needed (interfaces are similar)
2. **Type Safety**: Need to add TypeScript interfaces for events and state

## Implementation Notes

### Event Flow
```
WebSocket/API → Event Bus → Reducer → Store → Selector → UI
```

### Batching Strategy
- Events are queued for 100ms before processing
- Immediate mode available for critical updates
- Configurable batch delay per event type

### Memoization
- Selectors use length-based cache keys
- Manual cache invalidation when needed
- Consider LRU cache if memory becomes an issue

### Store Design
```javascript
class Store {
  state = [];
  subscribers = new Set();
  
  getState() { return this.state; }
  setState(newState) { 
    this.state = newState;
    this.notify();
  }
  subscribe(fn) { 
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }
}
```

## Performance Targets

- Event processing: < 1ms per event
- Selector computation: < 5ms for typical dataset
- Batch processing: < 50ms for 100 events
- Memory: < 10MB for 10k orders/fills

## Testing Strategy

1. **Unit Tests**: Test stores, selectors, and aggregators independently
2. **Integration Tests**: Test event flow from bus to UI
3. **Performance Tests**: Measure latency with synthetic load
4. **Stress Tests**: 1000 events/second for 60 seconds

## Future Enhancements

1. **Persistence**: Add IndexedDB persistence for stores
2. **Time Travel**: Implement snapshot/restore for debugging
3. **DevTools**: Build custom dev tools for event inspection
4. **Worker Thread**: Move event processing to Web Worker
5. **Incremental Updates**: Implement diff-based store updates

## References

- [Flux Architecture](https://facebook.github.io/flux/)
- [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
- [Observable Pattern](https://en.wikipedia.org/wiki/Observer_pattern)

## Decision Date
2025-01-09

## Decision Makers
- Architecture Team
- Frontend Engineers
- Performance Team
