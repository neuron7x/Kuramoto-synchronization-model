# Incident Response Lifecycle

This lifecycle standardises the way TradePulse responds to production incidents.
It is referenced by the production dashboard, SLA playbooks, and runbooks under
`docs/incident_playbooks.md`.

## 1. Detection

- Alerts fire via Prometheus or the production dashboard (`alerts` array).
- Operators acknowledge within five minutes and create an incident ticket using
  `reports/incidents/incident_report_template.md`.
- Tag the ticket with the alert ID (e.g. `cb-half-open`) and affected SLA.

## 2. Triage

- Review the production dashboard controls (`killSwitch`, `circuitBreaker`) to
  confirm the current state.
- Consult the relevant SLA playbook in [`docs/sla_alert_playbooks.md`](sla_alert_playbooks.md).
- Determine whether the kill switch or circuit breaker needs manual
  intervention.

## 3. Mitigation

- Execute the mitigation steps from the linked incident playbook.
- Record actions, timestamps, and responsible engineers in the incident ticket.
- If mitigation requires configuration changes, capture before/after snapshots
  of the production dashboard payload for auditability.

## 4. Communication

- Provide updates in `#status-tradepulse` every 15 minutes while the incident is
  active.
- Notify stakeholders listed in `stakeholders/communications_matrix.md` when the
  SLA is at risk.
- Update the ticket with customer impact, mitigation progress, and ETA.

## 5. Resolution

- Confirm dashboard metrics have returned to guardrails and no alerts are
  firing.
- Reset temporary overrides (kill switch, throttles) and document any residual
  risk.
- Close the incident ticket with links to logs, dashboard snapshots, and any
  patches deployed.

## 6. Post-Incident Review

- Complete the postmortem template in `reports/incidents/postmortem_template.md`
  within 48 hours.
- File corrective actions in `reports/incidents/action_item_register.md` and
  track to completion.
- Update runbooks or alert thresholds if gaps were identified.

Consistently following this lifecycle ensures every incident is measurable,
auditable, and feeds back into the preventative controls surfaced on the
production dashboard.
