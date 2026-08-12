# Production Cutover Readiness Checklist

This checklist captures the minimum operational guardrails required before authorising a production cutover for GeoSync. Treat it
as a living document — each item should be validated during the go/no-go rehearsal and revisited whenever major architecture or
process changes land.

## Service Level Objectives (SLOs)
- [x] **Error-rate guardrail defined** – `AutoRollbackGuard` enforces a 2% default error budget with configurable cooldowns.
- [x] **Latency SLO defined** – 500 ms p95 latency threshold encoded in `SLOConfig`, with float32 support for high-volume windows.
- [x] **Sliding-window evaluation** – Regression tests cover per-request ingestion and aggregated snapshot evaluation paths.
- [x] **Automated rollback hook** – Rollback callback tested for both error-rate and latency breaches, including cooldown handling.

## Monitoring & Alerting
- [x] **Operational metrics exported** – Kuramoto feature instrumentation emits structured metrics for collectors.
- [x] **Critical alerts mapped** – Alert runbooks reference the SLO triggers, GPU fallbacks, and secret-detector outputs.
- [x] **Fallback observability** – GPU and CPU indicator paths instrumented with warning logs to highlight degraded modes.
- [x] **Coverage guard** – Reliability-critical modules (`kuramoto`, `slo`, `security`) maintain >93% unit test coverage.

## On-Call Routines
- [x] **Rotation documented** – On-call escalation steps codified in `docs/monitoring.md` and linked from the readiness checklist.
- [x] **Runbook currency check** – Incident playbooks reviewed before cutover; checklist requires sign-off from duty engineer.
- [x] **Paging hygiene** – Checklist mandates quiet-hours testing of alert channels before switchover.

## Incident Playbooks
- [x] **Indicator degradation** – Kuramoto GPU fallback and CPU-only execution paths validated via dedicated unit tests.
- [x] **Data pipeline failures** – SLO guard exercises include sparse-sample and cooldown scenarios to prevent alert fatigue.
- [x] **Secret leakage response** – Automated scanning with masked output ensures security incidents are triaged safely.
- [x] **Cutover rollback drill** – Auto-rollback guard doubles as a rollback rehearsal script for cutover readiness.

> ✅ Use this checklist during the go/no-go meeting. Any unchecked item must be accompanied by an explicit risk acceptance from the
> engineering lead and recorded in `reports/release_readiness.md`.
