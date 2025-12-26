# Live Trading Runbook

This runbook documents the operational procedures for running the live execution
stack backed by `execution.live_loop.LiveExecutionLoop`. It is intended for
operators who are responsible for starting, monitoring, and shutting down live
trading sessions.

## Pre-Flight Checklist

1. **Infrastructure readiness** – confirm that market data feeds, network
   routes, and authentication secrets are available for every configured
   exchange connector.
2. **Risk controls** – verify that the `RiskManager` limits reflect the latest
   risk committee directives and that the kill-switch has been reset after the
   previous trading session (use `GET /admin/kill-switch` followed by
   `DELETE /admin/kill-switch` if required).
3. **State directory** – ensure the state directory configured in
   `LiveLoopConfig.state_dir` is writable and backed up. Historical OMS state
   files are required for warm restarts and forensic analysis.
4. **Metrics and logging** – confirm that the Prometheus collector and log
   aggregation pipelines are running to capture structured events emitted by
   the live loop.

## Cold Start Procedure

Cold starts are used when deploying a new strategy instance or when the prior
state is intentionally discarded.

1. **Initialise the loop**
   ```python
   from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
   from execution.risk import RiskLimits, RiskManager

   config = LiveLoopConfig(state_dir="/var/lib/tradepulse/live")
   risk = RiskManager(RiskLimits(...))
   loop = LiveExecutionLoop({"binance": binance_connector}, risk, config=config)
   loop.start(cold_start=True)
   ```
2. **Hydrate OMS from disk** – the cold start path reloads persisted OMS state
   and clears transient in-memory queues. Any outstanding open orders will be
   re-registered for fill tracking.
3. **Submit orders** – use `loop.submit_order(venue, order, correlation_id)` to
   enqueue new orders. The background submission thread handles placement and
   retries.
4. **Monitor metrics** – dashboards should display the
   `live_loop.*` structured logs, order placement metrics, and per-venue
   heartbeat gauges.

## Warm Start / Restart Procedure

Warm starts resume trading after a controlled shutdown or short outage.

1. **Instantiate with persisted state** – reuse the existing state directory
   and connectors when constructing `LiveExecutionLoop`.
2. **Start in warm mode** – call `loop.start(cold_start=False)`. The live loop
   will:
   - Load persisted OMS state including queued and outstanding orders.
   - Fetch `open_orders()` from each connector to reconcile venue state.
   - Re-enqueue orders that were persisted but missing on the venue.
   - Adopt orphaned venue orders into the OMS to maintain risk accounting.
3. **Validate reconciliation** – check logs for `live_loop.requeue_order` and
   `live_loop.adopt_order` events to confirm that discrepancies were addressed.
4. **Resume trading** – orders can be submitted immediately after the warm
   start completes.

## Monitoring and Observability

- **Structured logs** – the loop emits JSON-friendly logs such as
  `live_loop.order_processed`, `live_loop.register_fill`, and
  `live_loop.heartbeat_retry`. Forward these to the incident dashboard.
- **Metrics** – Prometheus counters and gauges are updated via
  `core.utils.metrics` for order placements, acknowledgements, fills, and
  positions. Ensure dashboards alert on stalled submissions or missing heartbeats.
- **Lifecycle hooks** – subscribe to `on_kill_switch`, `on_reconnect`, and
  `on_position_snapshot` to integrate with alerting or downstream systems.

### API Health Probe Interpretation

- Use `GET /health` before enabling traffic to the inference API or live loop.
  A `200` response with `"status": "ready"` indicates that the risk manager,
  cache, rate limiters, and declared dependencies are within SLO. Any `503`
  response requires intervention before proceeding.
- The `risk_manager` component reports the kill-switch state. When
  `status="failed"` or `healthy=false`, the kill-switch is engaged and the
  detailed reason is surfaced in the `detail` field. Reset the kill-switch via
  the admin API before resuming trading.
- Dependency probes are emitted as `dependency:<name>` components. Failures are
  reported with `status="failed"` and a descriptive message (for example,
  `connection refused`). Investigate upstream services (Kafka, Postgres, market
  data feeds) before retrying.
- `client_rate_limiter` and `admin_rate_limiter` components expose utilisation
  metrics and saturated keys. Repeated saturation should trigger incident
  handling to avoid throttling critical traffic.
- The `inference_cache` component reports occupancy of the TTL cache. A
  `degraded` status indicates the cache is full and requests will skip the fast
  path until entries expire; purge or expand the cache capacity if this state
  persists.

## Failure Handling

- **Connector disconnects** – heartbeat failures trigger exponential backoff
  retries and emit `on_reconnect` events. Investigate repeated retries and be
  prepared to fail over if the venue remains unreachable.
- **Order discrepancies** – warm start reconciliation produces warnings when
  orders are re-queued or adopted. Operators should confirm that downstream
  systems (P&L, hedging) reflect the corrected state.
- **Kill-switch activation** – when the risk kill-switch triggers, the live loop
  stops all background tasks, emits `on_kill_switch`, and requires manual
  intervention before restarting. Investigate the root cause, consult the
  [kill-switch failover runbook](runbook_kill_switch_failover.md) if the
  PostgreSQL state store is impaired, confirm the current status with
  `GET /admin/kill-switch`, and only resume once `DELETE /admin/kill-switch`
  records a successful reset event.

## Shutdown Procedure

1. Call `loop.shutdown()` to stop background workers and disconnect connectors.
2. Confirm that no orders remain queued and that OMS state files were persisted.
3. Archive logs and metrics for the session as part of the post-trade review.

## Idempotent Order Submission and Recovery

### Overview

The live execution loop now implements production-hardening features to ensure
resilient order lifecycle management:

- **Idempotent submissions** – every order submission carries an idempotency key
  (derived from `correlation_id` or a deterministic hash). Retries are
  deduplicated so only one placement reaches the venue.
- **Order ledger** – append-only JSONL at `<state_dir>/order_ledger.jsonl`
  records `submit/ack/fill/cancel/reject` events with monotonically increasing
  offsets and timestamps.
- **OMS snapshots** – periodic snapshots at `<state_dir>/oms_snapshots/*.json`
  include `ledger_offset`, OMS state, risk limits, and a checksum for integrity
  verification.
- **Recovery** – on warm start, the loop restores the last snapshot, replays the
  ledger from the last offset, reconnects with jittered backoff, and adopts any
  venue-open orders not present in the OMS.

### Idempotency Keys

Order submissions automatically generate idempotency keys:
- If a `correlation_id` is provided, the key is `corr:{correlation_id}`.
- Otherwise, a deterministic hash is computed from order attributes (symbol,
  side, quantity, price) bucketed by minute.

Duplicate submissions with the same idempotency key within the same venue will
be deduplicated at the connector level, ensuring no duplicate orders reach the
exchange.

### Order Ledger

The order ledger (`order_ledger.jsonl`) is an append-only journal capturing every
order lifecycle event:

```json
{
  "sequence": 42,
  "event": "submit",
  "timestamp": "2025-11-03T13:45:00Z",
  "order_id": "abc123",
  "correlation_id": "corr:my-order",
  "metadata": {...},
  "digest": "sha256:..."
}
```

- **Sequence numbers** are monotonically increasing and used to replay events
  after a snapshot.
- **Digests** form a hash chain for integrity verification during replay.

### OMS Snapshots

OMS snapshots are persisted periodically (default: every 30 seconds, configurable
via `LiveLoopConfig.snapshot_interval`) using atomic temp-write-then-rename to
avoid partial files:

```json
{
  "mode": "live",
  "ts": 1730642700.123,
  "ledger_offset": 42,
  "oms": {
    "ledger_offset": 42,
    "venues": {
      "binance": {
        "order-123": {
          "status": "ack",
          "last_update": 1730642695.0,
          "order": {...}
        }
      }
    },
    "checksum": "sha256:..."
  },
  "checksum": "sha256:..."
}
```

- Snapshots are stored at `<state_dir>/oms_snapshots/oms_snapshot_{timestamp}.json`.
- The last 5 snapshots (newest timestamps) are retained deterministically; older
  snapshots are pruned with debug logs on cleanup failure.

### Recovery Procedure

When starting the live loop with `cold_start=False`, the recovery sequence is:

1. **Restore last snapshot** – load the most recent `oms_snapshot_*.json` file
   and reconstruct the OMS state.
2. **Replay ledger delta** – iterate through `order_ledger.jsonl` from the last
   snapshot offset to the current ledger tail, applying all events.
3. **Reconnect with backoff** – connectors reconnect using exponential backoff
   with full jitter (capped by `LiveLoopConfig.max_backoff`).
4. **Adopt stray orders** – query each venue for open orders via
   `connector.open_orders()` and adopt any orders not present in the OMS. These
   "stray" orders may have been placed in a previous session or by another
   process.
5. **Resume normal operation** – resubscribe to WebSocket streams, reseed
   positions, and begin processing new order submissions.

### Recovery SLOs

The recovery procedure targets the following operational SLOs:

- **Reconciliation time** – complete recovery (snapshot restore + ledger replay +
  stray adoption) within ≤ 2 seconds on standard hardware.
- **Zero orphan orders** – all venue-open orders are adopted into the OMS or
  explicitly cancelled by policy (configurable). No orders should be "lost"
  between sessions.
- **48-hour staging soak** – run a staging environment for 48 hours without
  duplicate submissions or missed fills, validated via idempotency keys and
  reconciliation logs.

### Operational Commands

**Check ledger health:**
```bash
# Verify ledger integrity
python -m execution.order_ledger verify <state_dir>/order_ledger.jsonl
```

**Inspect OMS snapshot:**
```bash
# View latest snapshot
cat <state_dir>/oms_snapshots/oms_snapshot_*.json | tail -1 | jq .
```

**Force snapshot creation:**
```python
# From Python REPL or admin script
loop._persist_oms_snapshot_if_needed()
```

### Troubleshooting

**Snapshot not restoring:**
- Check that `<state_dir>/oms_snapshots/` contains valid JSON files.
- Verify checksum integrity by comparing computed hash with stored checksum.
- Review logs for `live_loop.snapshot_restore_failed` events.

**Stray orders not adopted:**
- Confirm `cold_start=False` was used on restart.
- Check `live_loop.adopt_orders` log events for adoption count.
- Verify `connector.open_orders()` returns the expected orders.

**Duplicate order placements:**
- Ensure `correlation_id` is provided and consistent across retries.
- Check `IdempotentSubmitter` cache via logs or metrics.
- Review ledger for duplicate `submit` events with same `idempotency_key`.

**Reconnection storms:**
- Verify `max_backoff` is set appropriately (default 60s).
- Check for upstream connectivity issues or API rate limits.
- Review `live_loop.heartbeat_retry` events for backoff delays.

## Contacts and Escalation

- **Execution engineering on-call** – primary contact for connector incidents.
- **Risk management** – escalation path for kill-switch or limit breaches.
- **Operations** – responsible for scheduling and communication during planned
  maintenance windows.

Keep this runbook up to date alongside changes to `execution/live_loop.py` and
related operational tooling.
