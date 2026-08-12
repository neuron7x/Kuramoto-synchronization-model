# Release Validation Runbook

This runbook defines the release validation discipline for GeoSync. It
covers the readiness checks, automation, and governance required before a
release can move from staging to production. The procedures assume the release
is orchestrated through the standard CI/CD pipeline and that rollback assets are
continuously maintained.

## 1. Readiness Checklist

Complete every checklist item before requesting the go/no-go meeting. Owners
must record evidence in the decision log.

- [ ] **Artifact integrity** – container images, wheels, and infrastructure
  templates are signed and stored in the release registry. SBOM and provenance
  attestations are attached.
- [ ] **Change scope locked** – PR freeze is in effect. All merge requests in
  the release train are tagged `release-X.Y.Z` and linked to approved JIRA
  tickets.
- [ ] **Dependencies verified** – database migrations have been dry-run against
  the staging shadow copy using `make migrate-dry-run`. External API contracts
  have green provider/consumer pact runs.
- [ ] **Observability baselines** – dashboards listed in [Dashboards](#8-dashboards)
  show healthy staging metrics for the last 24 hours. Alerting rules have been
  tuned for the new release features.
- [ ] **Risk controls** – feature flags have default safe positions. Kill-switch
  tests (`python scripts/kill_switch_verify.py`) have executed within the last
  7 days. Regulatory sign-off captured for compliance-impacting changes.
- [ ] **Data protection** – backfills, data migrations, or schema changes have
  backup/restore points. Snapshots stored in the release S3 bucket with
  retention ≥ 30 days.
- [ ] **Communication plan** – stakeholder announcement drafted and reviewed by
  operations. Support rotation briefed on release scope and recovery options.

## 2. Roles & Responsibilities

| Role | Primary Contact | Responsibilities |
| ---- | --------------- | ---------------- |
| Release Captain | Release engineering on-call | Chairs go/no-go, ensures checklists and decision log are complete, coordinates announcements. |
| SRE Lead | SRE primary | Validates infrastructure readiness, monitors smoke/sanity runs, owns rollback execution. |
| QA Lead | Test engineering lead | Certifies automated test suites, signs off on exploratory and regression coverage. |
| Risk & Compliance | Risk officer | Confirms regulatory obligations, updates kill-switch thresholds, records compliance approvals. |
| Business Owner | Product lead | Confirms value delivery, approves release window, coordinates customer messaging. |

Escalation tree: Release Captain → SRE Lead → Director of Engineering → CTO.

## 3. Release Windows and Freeze Policy

1. **Primary window** – Tuesdays and Thursdays 13:00–15:00 UTC. Avoid overlapping
   with market opens/major macro events unless explicitly approved.
2. **Freeze window** – No production deploys Friday 18:00 UTC through Monday
   04:00 UTC unless approved emergency change with Risk Officer sign-off.
3. **Fallback window** – Maintain a 90-minute buffer post-release to execute
   rollback and confirm stability. Product owner ensures business coverage during
   this window.
4. **Timezone coordination** – Ensure at least two timezones represented in the
   on-call bridge to cover follow-the-sun support for 6 hours post-deploy.

## 4. Automation: Smoke & Sanity Testing

Automation executes in three phases. All runs must succeed before promotion.

1. **Pre-promotion smoke** – Trigger in staging by running `python
   scripts/smoke_e2e.py --output-dir reports/release-smoke/<release-id>` and `make
   test:fast`. These commands execute the deterministic end-to-end harness and the
   curated pytest fast suite used in CI. Archive the generated artifacts with the
   release ticket.
2. **Canary sanity** – After canary traffic is enabled, run `python -m scripts
   test --pytest-args tests/performance tests/observability` to execute latency,
   order throughput, and reconciliation checks. Metrics must remain within SLO ±5%
   for 30 minutes before promotion.
3. **Post-release guard** – During the first 60 minutes in production, stream
   telemetry with `kubectl logs -f deployment/geosync --since=10m` and watch
   the dashboards listed below. Any PagerDuty incident automatically pauses the
   pipeline and blocks further promotion until metrics stabilise.

All automation logs are archived under `s3://geosync-release-validation/<release-id>/`.

## 5. Exit Criteria

A release may be declared successful when all conditions hold:

- ✅ All checklists complete with evidence captured in the decision log.
- ✅ Pre-promotion, canary, and post-release automation succeeded with no
  high-severity defects.
- ✅ Production metrics show stability within baseline tolerance for the guard
  period.
- ✅ No outstanding Sev-2+ incidents or regressions reported by customers during
  the guard period.
- ✅ Runbook updates and ADRs merged for any architectural changes shipped.

The Release Captain records the success verdict and closes the runbook entry.

## 6. Rollback Criteria & Procedure

Initiate rollback when any of the following trigger:

- Smoke or sanity automation fails twice for the same stage without a verified
  external cause.
- Critical KPI deviates >10% from baseline or error budget consumption exceeds
  5% within 30 minutes.
- Unrecoverable schema or state migration failure detected (apply
  `alembic downgrade -1` from the repository root).
- Security or compliance breach identified post-release.

**Rollback steps**

1. Engage the rollback bridge (`#release-rollback` channel) and page SRE Lead.
2. Freeze further changes by disabling continuous deployment workflows.
3. Redeploy the previous tag with `kubectl rollout undo deployment/geosync
   --to-revision=<revision>` (or rerun the deployment pipeline with the prior
   artifact). This reverts the application to the last known good configuration
   and refreshes the supporting infrastructure state.
4. Validate health by rerunning `python scripts/smoke_e2e.py` against the prior
   release and capturing fresh artifacts in the decision log.
5. Update dashboards and confirm alert recovery. Document root cause in the
   decision log and create an incident ticket if severity ≥ 2.

## 7. Configuration Change Control

- Maintain a config manifest for every deploy (`configs/releases/<release-id>.yaml`).
- All config changes must be peer-reviewed, version-controlled, and referenced in
  the release ticket.
- Use `scripts/config_diff.py --release <id>` to compare staging vs production
  configuration. No divergence is allowed without a signed exception.
- Store applied config hashes in the decision log. Hash mismatches invalidate the
  release until corrected.

## 8. Decision Log Template

The release captain owns the log and stores it in
`reports/release-decisions/<release-id>.md`.

```markdown
# Release <id> Decision Log

- **Release date/time (UTC):**
- **Participants:**
- **Scope summary:**
- **Evidence links:**
  - Readiness checklist:
  - Smoke/sanity runs:
  - Config diff report:
  - Dashboards:
- **Go/No-Go Decision:**
- **Rollback executed:** Yes/No (details)
- **Post-release notes:**
- **Outstanding risks/debt:**
```

## 9. Dashboards

All participants must have the following dashboards open during the release
window:

| Dashboard | Link | Purpose |
| --------- | ---- | ------- |
| Release Control Center | Grafana: `https://grafana.geosync.internal/d/release-control` | Aggregate smoke results, canary metrics, deployment timeline. |
| Trading Health | Grafana: `https://grafana.geosync.internal/d/trading-health` | Execution latency, order success rates, venue error budgets. |
| Market Data Integrity | Grafana: `https://grafana.geosync.internal/d/market-data` | Feed staleness, schema drift, ingest lag. |
| Risk & Limits | Grafana: `https://grafana.geosync.internal/d/risk-limits` | Kill-switch state, exposure per venue, compliance alerts. |
| Customer Impact | Looker: `https://looker.geosync.internal/dashboards/customer-impact` | Session errors, support ticket volume, major customer KPIs. |

Ensure access is granted ahead of the release window and that dashboard alerts
are synchronized with PagerDuty routes.

## 10. Continuous Improvement

- Conduct a release retrospective within 48 hours, covering automation gaps,
  rollback drills, and config change governance.
- Update this runbook whenever automation, tooling, or governance processes
  change. Tag the update in the next release checklist to confirm awareness.

