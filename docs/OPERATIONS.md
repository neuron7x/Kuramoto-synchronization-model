# Operations Guide: Thermodynamic Validation and Progressive Rollout

This runbook explains how to triage failures in the thermodynamic validation
(`validate-energy`) and Progressive Release Gates workflows.

## Reading `validate-energy` Failures

1. Download the artifacts from `.ci_artifacts/energy_validation.json`.
2. Inspect `free_energy`, `internal_energy`, and `entropy`.
   - If `free_energy` > 1.35 the validator rejected the build.
   - Review `penalties` to determine which metric exceeded its normalised limit.
3. Cross-reference the metric with production dashboards for corroborating data.
4. File an incident if the degradation also appears in production telemetry.

## Restoring Service Without Downtime

- Deploy the latest healthy build to the **Blue** slice while the **Green**
  slice continues to serve traffic.
- Apply the remedial patch to the Blue slice and monitor the energy metrics for
  two consecutive five-minute windows.
- When the free energy stays below 1.35 and no release gate fails, promote Blue
  to primary and keep Green on standby.

## Approving Changes That Increase `F`

1. Capture the post-change telemetry snapshot and attach
   `.ci_artifacts/energy_validation.json` to the release ticket.
2. Obtain approval from both the Thermodynamic Duty Officer and the responsible
   Platform Staff Engineer (see `docs/TACL.md`).
3. Record the justification in `release-notes.md` under the "Thermodynamic
   Changes" section to maintain the audit trail.

## Manual Rollout Confirmation

When automated rollback triggers, the controller writes `e2e_rollout_summary.json`
with the failing gate reasons.  To manually confirm the fix:

1. Re-run `python -m tacl.validate --run smoke` against the patched build.
2. Execute `python -m tacl.release_gates --config ci/release_gates.yml` and check
   that all gates report `"passed": true`.
3. Launch the Blue/Green stage manually if required by executing the GitHub
   Actions workflows:
   - `thermodynamic-validation.yml`
   - `progressive-release-gates.yml`
   - `progressive-rollout-blue-green.yml` (if a custom workflow exists)
4. Verify the canary ramp-up in the deployment dashboard and ensure the audit
   log contains the automatic rollback entry for regression tests.

## Scenario: Dual-Venue Market Data Degradation

When upstream venues diverge or a regional POP experiences packet loss, GeoSync
must continue to produce signals without contaminating the shared feature store.
Follow this scenario end-to-end before promoting any emergency patch:

1. **Detect** the degradation using the multi-venue freshness tiles in
   [`observability/dashboards/geosync-overview.json`](../observability/dashboards/geosync-overview.json).
   Trigger the synthetic heartbeat drill by running:

   ```bash
   geosync-cli metrics query 'max by (venue) (geosync_market_data_freshness_seconds{venue=~"(CBOE|NASDAQ)"})'
   ```

2. **Contain** the issue by isolating the affected venue. Flip the
   `ingestion.<venue>.enabled=false` feature flag via the control plane API and
   confirm the change propagated with `geosync-cli ingestion status`.
3. **Protect** downstream consumers by executing the quarantine workflow in
   [`docs/runbook_data_incident.md`](runbook_data_incident.md), ensuring the
   golden dataset buckets are tagged and backfills are paused.
4. **Stabilise** calculations by forcing the feature store to rescan the last
   30 minutes of uncorrupted data:

   ```bash
   geosync-cli feature-store repair --dataset market_data --window 30m --mode append
   ```

5. **Validate** signals by running the short-horizon replay against the clean
   venue and diffing the signal envelope:

   ```bash
   geosync-cli replay --strategy <id> --venues NASDAQ --since 45m \
     --compare --baseline reports/live/$(date +%Y-%m-%d)/signals_baseline.json
   ```

6. **Document** the mitigation in `reports/live/<date>/sla_incidents.md` and
   attach the metric snapshots plus the updated feature flag audit log. Escalate
   to the incident commander if the clean venue cannot maintain
   `geosync_market_data_freshness_seconds < 60` for 10 consecutive minutes.

## Scenario: Cross-Exchange Failover Rehearsal

Exercise this scenario weekly to ensure the playbooks, credentials, and SLA
alerts remain deployable without manual heroics:

1. **Prepare** sandbox orders by scheduling the `failover-sim` workflow in
   GitHub Actions (`.github/workflows/failover-sim.yml`). The workflow provisions
   dry-run orders against the backup exchange adapter.
2. **Execute** a controlled cutover using the live trading runbook but swap the
   adapter with `--exchange backup-1` and preload the approved credential bundle
   from `secrets/exchange/backup-1.json`.
3. **Monitor** the SLA packet:
   - `geosync_order_fill_latency_seconds` (p95 < 180ms)
   - `geosync_exchange_reject_ratio` (< 0.75%)
   - `geosync_position_drift_ratio` (< 0.5%)

   Use the canned dashboard `observability/dashboards/failover-drill.json` to
   visualise adherence.
4. **Reconcile** the reconciliation stream by invoking:

   ```bash
   geosync-cli reconciliation diff --exchange backup-1 --window 15m --output reports/live/$(date +%Y-%m-%d)/recon.json
   ```

   Investigate any non-zero drift with the risk officer before concluding the
   drill.
5. **Restore** the primary exchange by re-enabling the original adapter and
   confirming both venues show healthy heartbeats for 15 minutes. Attach the
   reconciliation report, Grafana screenshots, and credential rotation receipts
   to the change ticket.
