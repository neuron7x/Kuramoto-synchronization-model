# TradePulse Sandbox Demonstration Stack

This directory contains an isolated docker-compose specification that boots a
self-contained TradePulse demonstration environment. The stack wires a mock
market data feed, signal generation core, risk engine, paper execution service,
and a control plane offering kill-switch, health, and audit capabilities. No
external market connectivity or production secrets are required; the entire
system can run offline for safe third-party demos.

## Services

| Service | Purpose | Internal Port |
| --- | --- | --- |
| `mock-market` | Generates deterministic synthetic prices for supported symbols. | 8000 |
| `signal-core` | Derives directional signals from the mock market feed. | 8001 |
| `risk-engine` | Applies deterministic risk limits and integrates the kill-switch. | 8002 |
| `execution-paper` | Executes orders in paper mode using the signal and risk stack. | 8003 |
| `control-api` | Central control plane: kill-switch, health aggregation, audit feed. | 8004 |

Only the control API and paper execution services are published to the host via
`localhost:8004` and `localhost:8003` respectively. All other communication
remains on the isolated internal network.

## Usage

```bash
cd sandbox
docker compose up --build
```

Once running:

- Inspect aggregated health: `curl http://localhost:8004/health`
- Trigger the kill-switch: `curl -XPOST http://localhost:8004/kill-switch/engage -d '{"reason": "demo"}' -H 'Content-Type: application/json'`
- Submit a paper order: `curl -XPOST http://localhost:8003/orders -d '{"symbol": "btcusd", "side": "buy", "quantity": 1.5}' -H 'Content-Type: application/json'`
- Review the audit feed: `curl http://localhost:8004/audit/feed`

To stop the environment run `docker compose down`. All state is ephemeral and
stored in-memory to avoid accidental leakage of production secrets.
