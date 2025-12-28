# Runbook: Inference Service Degradation

## Purpose

Provide a repeatable response for incidents impacting online model inference
availability, latency, or output quality.

## Scope

Applies to model-serving endpoints, real-time feature assembly, and online
scoring pipelines used by live trading and downstream strategy runtime.

## Detection Triggers

Initiate this runbook when any of the following conditions occur:

- **SLO breach** for model inference latency or availability (see
  [`docs/reliability.md`](reliability.md#service-level-objectives)).
- **Alerting**: `tradepulse_model_inference_error_ratio` above threshold or
  sustained p95 latency regression in
  `tradepulse_model_inference_latency_quantiles_seconds`.
- **Quality regression**: `tradepulse_model_quality_degradation_events_total`
  increases or model-score distribution shifts on the model monitoring dashboard.

## Required Dashboards & Logs

- Grafana: `observability/dashboards/tradepulse-production-operations.json`
- Grafana: `observability/dashboards/tradepulse-latency-insights.json`
- Model monitoring jobs in `observability/model_monitoring.py`
- Drift monitors in `observability/drift.py`

## Triage Checklist (First 10 Minutes)

1. **Confirm blast radius**
   - Identify impacted models (`model_name` label) and endpoints.
   - Compare baseline vs current latency and error ratio.
2. **Validate upstream dependencies**
   - Feature store freshness and ingestion lag.
   - Queue depth/backpressure (if inference is async).
3. **Check resource saturation**
   - GPU/CPU utilization metrics (`tradepulse_model_gpu_percent`,
     `tradepulse_model_cpu_percent`).
4. **Inspect recent changes**
   - Last deploy, config changes, feature flag toggles, or canary rollouts.

## Mitigation Actions

Execute in order, stopping when the system stabilizes:

1. **Enable safe mode**
   - Reduce model concurrency, cap batch sizes, and enable cached inference if
     available.
2. **Scale inference capacity**
   - Increase replicas or GPU slots for the affected model pool.
3. **Throttle or shed non-critical traffic**
   - Gate low-priority calls (shadow traffic, analytics).
4. **Rollback the model or serving config**
   - Follow [`docs/runbook_model_rollback.md`](runbook_model_rollback.md).

## Validation After Mitigation

- p95 inference latency back within SLO.
- Error ratio at or below target.
- No drift alerts firing for critical features.
- Downstream order latency and risk gates stable.

## Communications

- Post status update in incident channel every 15 minutes.
- Notify Quant and SRE leads if rollback initiated or quality degradation is
  detected.

## Post-Incident Tasks

- Attach dashboards and metric snapshots to the incident report.
- Create a follow-up item to update guardrails or feature drift thresholds.
- Schedule a drill if the mitigation required manual intervention.
