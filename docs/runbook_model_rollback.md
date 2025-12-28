# Runbook: Model Rollback

## Purpose

Provide a standardized procedure to revert an online model to a previous,
known-good version after a regression, drift event, or operational incident.

## Triggers

- Inference availability or latency SLO breach.
- Quality degradation alerts or drift signals (see
  [`docs/runbook_data_drift_response.md`](runbook_data_drift_response.md)).
- Canary guardrail failure or error budget burn exceeding policy.

## Pre-Rollback Checklist

- Identify last known-good model version and artifact digest.
- Confirm rollback approval from on-call lead and model owner.
- Capture current metrics snapshot for incident records.

## Rollback Procedure

1. **Freeze promotions**
   - Pause any ongoing canaries or model promotions.
2. **Select target version**
   - Use the last stable model version from the release manifest or registry
     record.
3. **Deploy previous artifact**
   - Re-deploy the model service with the previous digest using the standard
     deployment pipeline (same command as a forward deploy, but with the older
     artifact).
4. **Warm caches**
   - Preload model weights and feature caches to reduce cold-start latency.
5. **Re-enable traffic**
   - Gradually restore traffic and monitor for stabilization.

## Verification

- Inference latency and error rate return to SLO targets.
- No new quality degradation or drift alerts.
- Downstream strategy metrics stable (signal latency, order latency).

## Communication and Audit

- Record rollback reason, timestamp, and target version in the incident ticket.
- Update release decision logs with the rollback evidence.
- Notify stakeholders when rollback is complete and validated.

## Post-Rollback Follow-ups

- Create a bug ticket with root cause hypotheses and reproduction steps.
- Schedule a regression test or chaos scenario to prevent recurrence.
