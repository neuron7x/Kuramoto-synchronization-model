# Runbook: Latency Degradation

## Purpose

Standardize response steps when latency SLOs are breached for order execution,
signal generation, or model inference pipelines.

## Triggers

- SLO burn rate alerts for latency in Prometheus/Grafana.
- p95 or p99 latency breaches in:
  - `geosync_order_ack_latency_quantiles_seconds`
  - `geosync_signal_to_fill_latency_quantiles_seconds`
  - `geosync_model_inference_latency_quantiles_seconds`
- Queue depth surges with sustained throughput drops.
- Hard-timeout events for execution or inference paths (see thresholds below).

## Latency Thresholds & Hard Timeouts

Use these thresholds as both alert triggers and guardrails for enforced
timeouts:

- **Pre-trade checks (OMS risk/compliance)**: 250ms hard timeout
  (`execution/oms.py` -> `OMSConfig.pre_trade_timeout`).
- **Pre-action policy gate (live loop)**: 200ms hard timeout
  (`execution/live_loop.py` -> `LiveLoopConfig.pre_action_timeout`).
- **Policy inference (runtime)**: 300ms hard timeout
  (`runtime/policy_deployment.py` -> `PolicyDeploymentManager.shadow_infer`).
- **Routing + venue execution**: 750ms hard timeout
  (`execution/router.py` -> `ExecutionRoute.operation_timeout`).

If these are tightened/relaxed for a venue or strategy, update this runbook and
the corresponding configuration source-of-truth.

## Immediate Actions (0–5 Minutes)

1. **Acknowledge alert** and open incident channel.
2. **Confirm impact**: identify which latency path is affected (ingestion,
   signal, inference, execution).
3. **Freeze non-critical deploys** and notify release manager.

## Diagnostic Steps

1. **Review latency breakdown** in
   `observability/dashboards/geosync-latency-insights.json`.
2. **Check for saturation**
   - CPU/memory on execution workers.
   - GPU utilization for model serving.
3. **Inspect queue metrics**
   - Queue depth and backlog growth rate.
4. **Validate upstream dependencies**
   - Exchange connectivity, market data freshness, feature store lag.

## Mitigation Options

Apply the first effective option and re-check p95 latency:

1. **Enable backpressure controls**
   - Temporarily throttle order submission or ingestion backfill.
2. **Scale critical workers**
   - Increase replicas for execution, signal, or inference services.
3. **Activate degraded mode**
   - Reduce strategy complexity or disable optional features.
4. **Trigger rollback**
   - If regression correlates with a deploy, follow
     [`docs/runbook_model_rollback.md`](runbook_model_rollback.md) or the release
     rollback procedure in [`docs/RELEASE_PROCESS.md`](RELEASE_PROCESS.md).

## Fallback Triggers (Safe Mode)

Trigger safe mode when any of the following are observed:

- Pre-trade checks (risk/compliance) time out.
- Pre-action policy gates exceed timeout.
- Policy inference timeouts exceed the hard limit.
- Routing timeout breaches (primary + backup) or route throttling escalates.

Safe mode actions include:

- Switch strategy mode to **conservative** via the live loop.
- Block new orders when pre-trade checks time out.
- Use policy fallback handler (default: hold/neutral action).
- Allow routing failover to backup venues; if both time out, halt submissions.

## Recovery Flow

1. **Stabilize latency**
   - Ensure p95/p99 are below thresholds for 15+ minutes.
   - Confirm queue depth is decreasing.
2. **Clear safe mode**
   - Re-enable normal strategy mode only after backpressure clears.
   - Verify risk/compliance checks are completing under timeout.
3. **Validate execution**
   - Submit a low-notional canary order and confirm routing latency.
   - Verify model inference latencies (p95) are stable.
4. **Post-restore monitoring**
   - Watch for 30 minutes; keep rollback ready.
   - Capture logs for any fallback triggers during recovery.

## Verification

- Latency p95/p99 within target thresholds for at least 15 minutes.
- Error rate stable; no new SLO burn alerts.
- Queue depth returning to baseline.

## Post-Incident Actions

- Capture before/after latency charts in the incident report.
- Document the root cause and update guardrails if thresholds were too loose.
- Schedule chaos drill if the mitigation path was unclear or manual.
