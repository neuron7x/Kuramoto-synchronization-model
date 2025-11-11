import assert from 'assert';
import http from 'http';

import { DashboardDataClient } from '../src/core/index.js';

const SAMPLE_SNAPSHOT = {
  route: 'overview',
  header: { title: 'Demo', subtitle: 'Testing dashboard client' },
  overview: { github: { stars: 1 } },
  monitoring: { metrics: { grossExposure: { value: 1000, limit: 2000 } } },
  positions: { fills: [], orders: [], ticks: [] },
  orders: { orders: [{ order_id: 'ord-1' }], fills: [] },
  pnl: { pnlPoints: [], quotes: [] },
  signals: { signals: [] },
  community: { community: { metrics: {} } },
};

class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    FakeWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = FakeWebSocket.OPEN;
      if (typeof this.onopen === 'function') {
        this.onopen({ target: this });
      }
    }, 0);
  }

  simulateMessage(message) {
    const payload = typeof message === 'string' ? message : JSON.stringify(message);
    if (typeof this.onmessage === 'function') {
      this.onmessage({ data: payload });
    }
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    if (typeof this.onclose === 'function') {
      this.onclose({ target: this });
    }
  }
}

FakeWebSocket.CONNECTING = 0;
FakeWebSocket.OPEN = 1;
FakeWebSocket.CLOSING = 2;
FakeWebSocket.CLOSED = 3;
FakeWebSocket.instances = [];

async function withTestServer(handler) {
  const server = http.createServer((req, res) => {
    const url = (req.url || '').split('?')[0];
    if (req.method !== 'GET') {
      res.writeHead(405);
      res.end();
      return;
    }
    if (url === '/dashboard/snapshot') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(SAMPLE_SNAPSHOT));
      return;
    }
    const route = url.replace('/dashboard/', '');
    if (route in SAMPLE_SNAPSHOT) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(SAMPLE_SNAPSHOT[route]));
      return;
    }
    res.writeHead(404);
    res.end(JSON.stringify({ error: 'not-found' }));
  });

  await new Promise((resolve) => server.listen(0, resolve));
  const address = server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  try {
    await handler({ baseUrl });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

await withTestServer(async ({ baseUrl }) => {
  const client = new DashboardDataClient({ baseUrl });
  const snapshot = await client.fetchSnapshot();
  assert.strictEqual(snapshot.route, 'overview');
  assert.strictEqual(snapshot.orders.orders[0].order_id, 'ord-1');

  const ordersResponse = await client.fetchRoute('orders');
  assert.deepStrictEqual(ordersResponse.payload, SAMPLE_SNAPSHOT.orders);

  let threw = false;
  try {
    await client.fetchRoute('unknown');
  } catch (error) {
    threw = true;
  }
  assert.ok(threw, 'fetchRoute should reject unknown routes');
});

const streamingClient = new DashboardDataClient({
  baseUrl: 'http://localhost',
  WebSocketImpl: FakeWebSocket,
});

const received = [];
const subscription = streamingClient.subscribe({
  orders: (payload) => {
    received.push(payload);
  },
});

const fakeSocket = FakeWebSocket.instances[0];
fakeSocket.simulateMessage({ type: 'orders', payload: { orders: [{ order_id: 'stream-1' }] } });

assert.strictEqual(received.length, 1);
assert.strictEqual(received[0].orders[0].order_id, 'stream-1');

subscription.close();
