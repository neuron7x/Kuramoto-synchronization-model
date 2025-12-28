# Operational Readiness and Runbook Alignment

This guide unifies the operational checklists, scripts, and telemetry guardrails
required to declare TradePulse production-ready for a live trading session. Use
it as the control tower before, during, and after every activation. Each section
links to the authoritative artefacts already stored in the repository so
operators can move quickly without bypassing governance.

## 1. Pre-Launch Control Checklist

Complete this control list before triggering any deployment command. Record the
status in the release ticket and attach the evidence paths indicated below.

| Check | Owner | Evidence |
| ----- | ----- | -------- |
| ✅ Approvals confirmed (change ticket, risk sign-off, compliance memo) | Release Manager | `reports/change_manifest/<ticket>.md` |
| ✅ Release readiness pack reviewed | Release Manager | [`reports/release_readiness.md`](../reports/release_readiness.md) |
| ✅ Production cutover gate signed | Release Manager + Risk | [`reports/prod_cutover_readiness_checklist.md`](../reports/prod_cutover_readiness_checklist.md) |
| ✅ Health gate: CI + performance jobs green | Dev Lead | [`TESTING_SUMMARY.md`](../TESTING_SUMMARY.md) exports |
| ✅ Risk envelope verified | Risk Officer | `configs/risk/limits.yaml` diff attached to ticket |
| ✅ On-call rotation confirmed | SRE Captain | [`docs/reliability.md`](reliability.md#on-call-discipline) roster |
| ✅ Incident playbooks up to date | Incident Commander | [`docs/incident_playbooks.md`](incident_playbooks.md) review timestamp |

> **Go/No-Go rule:** Deployments without all seven artifacts attached are
> automatically downgraded to staging until evidence is complete.

## 2. Launch and Halt Scripts

TradePulse exposes CLI entry points that encapsulate the safe start/stop
sequence. Run every command from a locked workstation with shell history
preserved. Always capture stdout/stderr into the `reports/live/<date>/` folder.

```bash
# Launch (dry-run smoke, then promote)
tradepulse-cli deploy --env prod --strategy <strategy_id> --artifact <digest> \
  | tee "reports/live/$(date +%Y-%m-%d)/deploy.log"
tradepulse-cli validate --env prod --strategy <strategy_id> \
  --window "15m" --mode dry-run \
  | tee "reports/live/$(date +%Y-%m-%d)/validation.log"

# Planned stop
tradepulse-cli settle --strategy <strategy_id> \
  | tee "reports/live/$(date +%Y-%m-%d)/settle.log"

# Emergency halt (kill-switch)
tradepulse-cli kill --strategy <strategy_id> --reason "<text>" \
  | tee "reports/live/$(date +%Y-%m-%d)/kill.log"
```

Confirm the control plane feature flag (`live.enabled`) mirrors the intended
state at the end of each script. Include the flag change audit trail in the
session artefacts.

## 3. SLA Monitoring Packet

The on-call operator must watch the following telemetry group during the entire
session. Failure modes and escalation paths are defined in the live trading
runbook.

| Metric | Threshold | Source | Escalation |
| ------ | --------- | ------ | ---------- |
| Heartbeat (ingestion, feature store, execution) | No gaps >1 minute | [`observability/dashboards/tradepulse-overview.json`](../observability/dashboards/tradepulse-overview.json) | Page SRE on-call after 2 consecutive misses |
| Order latency (round-trip) | p95 < 120 ms | `metrics.execution.latency` | Trigger throttling; escalate to Execution Trader |
| Position drift vs target | <0.5% notional | `metrics.portfolio.drift` | Engage risk officer and evaluate halt |
| Risk service heartbeat | No gaps >3 cycles | `metrics.risk.heartbeat` | Initiate kill-switch preparation |

Document SLA breaches in `reports/live/<date>/sla_incidents.md` and cross-link
to the relevant incident ticket.

## 4. Integrated Runbook and Playbook References

Keep the following documents open during operations. They provide the extended
decision trees for the checkpoints summarised above.

- [`docs/runbook_live_trading.md`](runbook_live_trading.md) – Step-by-step launch
  and halt procedure, including emergency branches.
- [`docs/runbook_data_incident.md`](runbook_data_incident.md) – Data feed
  containment and recovery guidance.
- [`docs/runbook_secret_rotation.md`](runbook_secret_rotation.md) – End-to-end
  secret rotation procedure with Vault automation hooks.
- [`docs/runbook_secret_leak.md`](runbook_secret_leak.md) – Incident response
  plan for suspected credential exposure.
- [`docs/runbook_inference_incident.md`](runbook_inference_incident.md) –
  Inference service degradation response.
- [`docs/runbook_latency_degradation.md`](runbook_latency_degradation.md) –
  Latency regression response for critical paths.
- [`docs/runbook_model_rollback.md`](runbook_model_rollback.md) – Standardized
  model rollback procedure.
- [`docs/runbook_data_drift_response.md`](runbook_data_drift_response.md) –
  Data drift triage and remediation steps.
- [`docs/incident_playbooks.md`](incident_playbooks.md) – Communication and
  escalation expectations for high-severity events.
- [`docs/operational_handbook.md`](operational_handbook.md) – Governance context,
  CI guardrails, and dependency controls.

## 5. On-Call Discipline Enhancements

To strengthen handoffs, run this mini checklist at the start of every shift.

1. Review the open action items in `reports/live/<date>/todo.md`.
2. Confirm PagerDuty schedules match [`docs/reliability.md`](reliability.md)
   (swap shifts if necessary and record in ticket).
3. Trigger the PagerDuty heartbeat test described in
   [`docs/reliability.md`](reliability.md#alerting-and-escalation) and attach the
   confirmation screenshot to the ticket.
4. Walk through the communications plan in
   [`docs/incident_playbooks.md`](incident_playbooks.md#communications-matrix).

A shift is not considered accepted until all four steps are logged in the change
ticket.

## 6. Post-Session Archival Checklist

Archive every artefact needed for auditability and retrospectives before closing
the deployment ticket. Use `reports/live/<date>/` as the canonical folder.

- [ ] CLI outputs: `deploy.log`, `validation.log`, `settle.log`, `kill.log` (if
      invoked)
- [ ] Metrics snapshots exported from Prometheus as
      `metrics_<timestamp>.json.gz`
- [ ] Risk limit deltas stored as `risk_limits.yaml`
- [ ] Position, PnL, and exposure CSVs
- [ ] Incident reports or near-miss notes (`sla_incidents.md`, `postmortem.md`)
- [ ] Log bundles compressed via `tar -czf logs_<timestamp>.tar.gz observability/logs`
- [ ] Ticket updated with archive index and storage location hash

Do not delete the working directory until checksum verification is complete.
Use `scripts/runtime/checksum.py` to generate the manifest and attach it to the
ticket.

---

Revisit this document after every major incident review or tooling change. Keep
links updated and ensure evidence paths stay accurate to maintain audit-grade
operational readiness.
