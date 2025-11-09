import assert from 'node:assert';
import { 
  PrecisionPolicy, 
  ensureMs, 
  ensureFinite, 
  normalizeNumber 
} from '../src/core/precision.js';

console.info('[L7] precision policy tests');

// Test PrecisionPolicy
const policy = new PrecisionPolicy({
  currencyPrecision: 2,
  percentPrecision: 2,
  metricPrecision: 4,
});

assert.strictEqual(policy.round(1.2345, 2), 1.23, 'should round to 2 decimals');
assert.strictEqual(policy.round(1.2355, 2), 1.24, 'should round up correctly');
assert.strictEqual(policy.formatCurrency(1234.56), '$1,234.56', 'should format currency');
assert.strictEqual(policy.formatCurrency(10500), '$10,500', 'should format large currency without decimals');
assert.strictEqual(policy.formatPercent(0.256), '25.6%', 'should format percent');
assert.strictEqual(policy.formatPercent(0.025), '2.50%', 'should format small percent');
assert.strictEqual(policy.formatMetric(1.23456), '1.2346', 'should format metric');

// Test non-finite values
assert.strictEqual(policy.formatCurrency(NaN), '—', 'should handle NaN currency');
assert.strictEqual(policy.formatPercent(Infinity), '—', 'should handle Infinity percent');
assert.strictEqual(policy.formatMetric(-Infinity), 'n/a', 'should handle -Infinity metric');

// Test ensureMs
assert.strictEqual(ensureMs(1609459200), 1609459200000, 'should convert seconds to ms');
assert.strictEqual(ensureMs(1609459200000), 1609459200000, 'should keep ms as is');
assert.strictEqual(ensureMs(NaN), null, 'should return null for NaN');
assert.strictEqual(ensureMs(null), null, 'should return null for null');

// Test ensureFinite
assert.strictEqual(ensureFinite(42), 42, 'should return finite value');
assert.strictEqual(ensureFinite(NaN), 0, 'should return fallback for NaN');
assert.strictEqual(ensureFinite(Infinity, -1), -1, 'should return custom fallback');

// Test normalizeNumber
assert.strictEqual(normalizeNumber(5, { min: 0, max: 10 }), 5, 'should keep value in range');
assert.strictEqual(normalizeNumber(-5, { min: 0, max: 10 }), 0, 'should clamp to min');
assert.strictEqual(normalizeNumber(15, { min: 0, max: 10 }), 10, 'should clamp to max');
assert.strictEqual(normalizeNumber(NaN, { fallback: 5 }), 5, 'should use fallback for NaN');

console.log('precision policy tests passed');
