# Runbook: Latency Degradation

## Purpose

Standardize response steps when latency SLOs are breached for order execution,
signal generation, or model inference pipelines.

## Triggers

- SLO burn rate alerts for latency in Prometheus/Grafana.
- p95 or p99 latency breaches in:
  - `tradepulse_order_ack_latency_quantiles_seconds`
  - `tradepulse_signal_to_fill_latency_quantiles_seconds`
  - `tradepulse_model_inference_latency_quantiles_seconds`
- Queue depth surges with sustained throughput drops.

## Immediate Actions (0–5 Minutes)

1. **Acknowledge alert** and open incident channel.
2. **Confirm impact**: identify which latency path is affected (ingestion,
   signal, inference, execution).
3. **Freeze non-critical deploys** and notify release manager.

## Diagnostic Steps

1. **Review latency breakdown** in
   `observability/dashboards/tradepulse-latency-insights.json`.
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

## Verification

- Latency p95/p99 within target thresholds for at least 15 minutes.
- Error rate stable; no new SLO burn alerts.
- Queue depth returning to baseline.

## Post-Incident Actions

- Capture before/after latency charts in the incident report.
- Document the root cause and update guardrails if thresholds were too loose.
- Schedule chaos drill if the mitigation path was unclear or manual.
