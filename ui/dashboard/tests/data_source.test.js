import assert from 'assert';
import { DataSourceClient, createDataSource } from '../src/core/data_source.js';

console.info('[L7] Data source client tests');

// Test DataSourceClient construction
const client = new DataSourceClient({
  baseUrl: 'http://test.local/api',
  wsUrl: 'ws://test.local/api/ws',
  timeout: 5000,
  maxRetries: 2,
});

assert.strictEqual(client.baseUrl, 'http://test.local/api', 'baseUrl should be set');
assert.strictEqual(client.wsUrl, 'ws://test.local/api/ws', 'wsUrl should be set');
assert.strictEqual(client.timeout, 5000, 'timeout should be set');
assert.strictEqual(client.maxRetries, 2, 'maxRetries should be set');

// Test createDataSource factory
const factoryClient = createDataSource({ baseUrl: 'http://factory.local/api' });
assert.ok(factoryClient instanceof DataSourceClient, 'createDataSource should return DataSourceClient instance');
assert.strictEqual(factoryClient.baseUrl, 'http://factory.local/api', 'factory client baseUrl should be set');

// Test default values
const defaultClient = new DataSourceClient();
assert.ok(defaultClient.baseUrl, 'default baseUrl should be set');
assert.ok(defaultClient.wsUrl, 'default wsUrl should be set');
assert.ok(defaultClient.timeout > 0, 'default timeout should be positive');

// Test batch method with empty array
const emptyBatch = await defaultClient.batch([]);
assert.deepStrictEqual(emptyBatch, [], 'batch with empty array should return empty array');

// Test isConnected when not connected
assert.strictEqual(defaultClient.isConnected(), false, 'isConnected should be false when not connected');

// Test disconnect when not connected
defaultClient.disconnect();
assert.strictEqual(defaultClient.isConnected(), false, 'disconnect should work when not connected');

console.log('data source client tests passed');
