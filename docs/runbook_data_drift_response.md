# Runbook: Data Drift Response

## Purpose

Standardize the response to data drift in live features or model inputs to
protect inference quality and trading outcomes.

## Triggers

- Drift alerts from `observability/drift.py` (PSI/KS thresholds exceeded).
- Elevated `geosync_model_quality_degradation_events_total`.
- Feature distribution shifts observed in model monitoring dashboards.

## Triage Checklist

1. **Confirm the drift signal**
   - Identify features with PSI/KS breaches and severity.
   - Compare live distribution to reference window.
2. **Assess impact**
   - Review model quality metrics and downstream PnL/latency changes.
3. **Check data freshness**
   - Validate ingestion lag and data completeness.

## Containment Actions

1. **Freeze model promotions** and pause canary expansion.
2. **Switch to fallback features** or safe defaults (if available).
3. **Enable conservative mode**
   - Reduce strategy aggressiveness or throttle inference to protect risk.

## Remediation Steps

1. **Trace upstream sources**
   - Identify if drift originates from market feed changes, schema updates, or
     data gaps.
2. **Backfill or repair data**
   - Run data repair/backfill procedures (see
     [`docs/runbook_data_incident.md`](runbook_data_incident.md)).
3. **Recalibrate model**
   - Trigger retraining or refresh calibration for the impacted model family.
4. **Rollback if quality degraded**
   - Follow [`docs/runbook_model_rollback.md`](runbook_model_rollback.md).

## Validation

- Drift metrics return below thresholds for at least one full evaluation window.
- Model quality metrics stabilize.
- No new drift alerts for the affected features.

## Communication and Audit

- Update incident channel with drift summary and mitigation status.
- Record affected feature list, thresholds, and remediation steps in the
  incident report.
