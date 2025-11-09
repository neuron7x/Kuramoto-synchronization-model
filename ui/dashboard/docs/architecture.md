# Dashboard Architecture

## Overview

The TradePulse Dashboard follows a layered architecture pattern with clear separation of concerns between business logic, state management, and presentation.

## Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│                  UI Layer (views/)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  Orders     │  │  Positions  │  │   Signals   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────┐
│              UI Components (components/)             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ LiveTable   │  │  AreaChart  │  │   Router    │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────┐
│            Services Layer (services/)                │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Event Bus   │  │   Stores     │  │ Selectors │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
└─────────────────────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────┐
│            Domain Layer (domain/)                    │
│  ┌─────────────────────────────────────────────────┐│
│  │         Business Aggregators                     ││
│  │  • aggregatePositions                            ││
│  │  • buildOrderRows                                ││
│  │  • aggregateBacktests                            ││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────┐
│              Core Utilities (core/)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │Formatters│  │Telemetry │  │Sanitize  │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│  ┌──────────┐  ┌──────────┐                        │
│  │Precision │  │Dashboard │                        │
│  └──────────┘  └──────────┘                        │
└─────────────────────────────────────────────────────┘
```

## Data Flow

### Event Processing

```
┌────────────┐
│Raw Events  │ (WebSocket, API)
└─────┬──────┘
      │
      ▼
┌─────────────────┐
│  Event Bus      │ ◄── Batching (100ms)
│  processEvent() │
└─────┬───────────┘
      │
      ├──► Reducer (normalize)
      │
      ▼
┌─────────────────┐
│    Stores       │
│ • ordersStore   │
│ • fillsStore    │
│ • ticksStore    │
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│   Selectors     │ ◄── Memoization
│ (derived state) │
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│  UI Components  │
│   (re-render)   │
└─────────────────┘
```

### State Updates

1. **Event Reception**: Raw events arrive from WebSocket or API
2. **Normalization**: Events are normalized via reducers
3. **Store Update**: Normalized data updates stores
4. **Selector Computation**: Selectors compute derived state (memoized)
5. **UI Update**: Components subscribe to state changes and re-render

## Key Components

### Domain Layer

**Aggregators** (`domain/aggregators.js`)
- `aggregatePositions(fills, orders, ticks)`: Compute positions from fills
- `buildOrderRows(orders, fills)`: Enrich orders with fill progress
- `aggregateBacktests(backtests, metric)`: Rank backtest results
- `normalizeEvent(rawEvent)`: Normalize raw events to internal format

### Services Layer

**Event Bus** (`services/event-bus.js`)
- Centralized event processing with reducers
- Event batching (100ms coalescing)
- Pub/sub for state updates

**Stores** (`services/stores.js`)
- `OrdersStore`: Manages order state
- `FillsStore`: Manages fill/execution state
- `TicksStore`: Manages market data ticks
- Base `Store` class with subscribe/notify

**Selectors** (`services/selectors.js`)
- `positionsSelector()`: Derives positions from stores
- `backtestsSelector(backtests, metric)`: Ranks backtests
- `ordersWithProgressSelector()`: Enriches orders with progress
- Memoization for performance

### Core Utilities

**Precision** (`core/precision.js`)
- `PrecisionPolicy`: Unified formatting policy
- `ensureMs(timestamp)`: Normalize timestamps to milliseconds
- `ensureFinite(value, fallback)`: Validate finite numbers
- `normalizeNumber(value, bounds)`: Clamp values to range

**Sanitization** (`core/sanitize.js`)
- `sanitizeHtml(html)`: Whitelist-based HTML sanitization
- `escapeHtml(value)`: Escape HTML entities
- `stripHtml(html)`: Remove all HTML tags
- `sanitizeUrl(url)`: Validate and sanitize URLs

**Telemetry** (`core/telemetry.js`)
- Event emission with timestamps
- Traceparent generation and propagation
- Browser-compatible crypto fallback

## Performance Optimizations

### Memoization
Selectors use memoization to avoid recomputing derived state when inputs haven't changed. Cache keys are based on array lengths and timestamps.

### Event Batching
The Event Bus batches events with 100ms coalescing to reduce update frequency and improve performance.

### Incremental Updates
Stores support incremental updates via `updateState()` to avoid full re-renders.

## Best Practices

### State Management
1. Never mutate state directly
2. Use stores for all state updates
3. Derive state through selectors
4. Subscribe to stores for reactive updates

### Event Processing
1. Normalize events in reducers
2. Validate all input data
3. Use ensureMs for timestamps
4. Use ensureFinite for numeric values

### Security
1. Always sanitize HTML content
2. Escape user input
3. Validate URLs before rendering
4. Use CSP headers (script-src with nonce)

### Performance
1. Use memoized selectors
2. Batch events when possible
3. Avoid unnecessary re-renders
4. Use virtualization for large lists

## Future Enhancements

- [ ] Row virtualization for tables
- [ ] Web Workers for heavy computations
- [ ] Incremental diff updates
- [ ] Performance monitoring with marks/measures
- [ ] Dynamic event sampling
- [ ] Advanced telemetry with span links
