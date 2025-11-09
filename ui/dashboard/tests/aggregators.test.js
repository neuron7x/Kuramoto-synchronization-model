import assert from 'node:assert';
import {
  aggregatePositions,
  buildOrderRows,
  aggregateBacktests,
  normalizeEvent,
} from '../src/domain/aggregators.js';

console.info('[L7] domain aggregators tests');

const now = Date.now();

// Test aggregatePositions
const fills = [
  {
    event_id: 'fill-1',
    symbol: 'AAPL',
    timestamp: now - 60000,
    order_id: 'ord-1',
    fill_id: 'fill-1',
    filled_qty: 100,
    fill_price: 150.5,
    metadata: { side: 'BUY' },
  },
  {
    event_id: 'fill-2',
    symbol: 'AAPL',
    timestamp: now - 30000,
    order_id: 'ord-2',
    fill_id: 'fill-2',
    filled_qty: 50,
    fill_price: 151.0,
    metadata: { side: 'SELL' },
  },
];

const ticks = [
  { symbol: 'AAPL', last_price: 152.0, timestamp: now },
];

const positions = aggregatePositions(fills, [], ticks);
assert.strictEqual(positions.length, 1, 'should create one position for AAPL');
assert.strictEqual(positions[0].symbol, 'AAPL');
assert.strictEqual(positions[0].netQuantity, 50, 'should calculate net quantity');
assert.ok(positions[0].currentPrice > 0, 'should have current price from tick');
assert.ok(positions[0].exposure > 0, 'should calculate exposure');

// Test buildOrderRows
const orders = [
  {
    event_id: 'order-1',
    order_id: 'ord-1',
    symbol: 'AAPL',
    quantity: 100,
    timestamp: now - 120000,
  },
];

const orderRows = buildOrderRows(orders, fills);
assert.strictEqual(orderRows.length, 1, 'should create one order row');
assert.strictEqual(orderRows[0].totalFilled, 100, 'should sum filled quantity');
assert.strictEqual(orderRows[0].progress, 1, 'should calculate progress as 100%');
assert.strictEqual(orderRows[0].remaining, 0, 'should calculate remaining as 0');

// Test aggregateBacktests
const backtests = [
  {
    metadata: { id: 'bt-1', strategy: 'momentum' },
    metrics: { sharpe: 2.5, pnl: 5000 },
  },
  {
    metadata: { id: 'bt-2', strategy: 'mean_revert' },
    metrics: { sharpe: 1.8, pnl: 3000 },
  },
  {
    metadata: { id: 'bt-3', strategy: 'trend' },
    metrics: { sharpe: 3.1, pnl: 7000 },
  },
];

const result = aggregateBacktests(backtests, 'sharpe');
assert.strictEqual(result.metric, 'sharpe');
assert.strictEqual(result.ranking.length, 3);
assert.strictEqual(result.best.strategy, 'trend', 'should identify best strategy');
assert.strictEqual(result.worst.strategy, 'mean_revert', 'should identify worst strategy');
assert.ok(
  result.ranking[0].score >= result.ranking[1].score,
  'should sort by score descending'
);

// Test normalizeEvent
const rawEvent = {
  event_id: 'evt-1',
  schema_version: '2',
  timestamp: 1609459200,
  type: 'ORDER',
  symbol: 'AAPL',
};

const normalized = normalizeEvent(rawEvent);
assert.strictEqual(normalized.eventId, 'evt-1');
assert.strictEqual(normalized.schemaVersion, '2');
assert.strictEqual(normalized.timestamp, 1609459200000, 'should convert timestamp to ms');
assert.strictEqual(normalized.type, 'ORDER');

// Test edge cases
assert.strictEqual(aggregatePositions([], [], []).length, 0, 'should handle empty arrays');
assert.strictEqual(buildOrderRows([], []).length, 0, 'should handle empty orders');
assert.strictEqual(normalizeEvent(null), null, 'should handle null event');

console.log('domain aggregators tests passed');
