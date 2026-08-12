# Kill-Switch Store Failover Runbook

## Purpose

This runbook documents the operational procedures for failing over the
kill-switch state store when the primary PostgreSQL instance becomes unavailable.
The guidance complements the live trading runbook and should be used during
incident response, planned maintenance, or disaster recovery exercises.

## Preconditions

- The `kill_switch_state` table has been deployed using the migrations in
  `migrations/postgres/`.
- Application nodes are configured with the PostgreSQL-backed
  `PostgresKillSwitchStateStore` via the `GEOSYNC_KILL_SWITCH_POSTGRES__*`
  environment variables.
- Replica instances are in sync and accept read/write traffic for the
  `kill_switch_state` table.

## Failover Checklist

1. **Detect and confirm the incident**
   - Monitor the API readiness probe (`/healthz`) for degraded or failed
     status. A `kill_switch` component marked as `failed` with details such as
     "connection refused" indicates loss of the primary database.
   - Correlate with PostgreSQL monitoring (Patroni, managed service metrics) to
     confirm the failure mode.

2. **Engage the platform team**
   - Notify on-call engineering and the risk committee per the escalation plan
     in `docs/runbook_live_trading.md`.
   - Pause automated trading flows if the kill-switch cannot be read within the
     configured staleness window (default 5 minutes).

3. **Promote a replica**
   - Use your PostgreSQL HA tooling (e.g., Patroni, managed database failover)
     to promote the healthiest replica.
   - Validate that the promoted node has the latest `kill_switch_state` row by
     running:

     ```sql
     SELECT engaged, reason, updated_at FROM kill_switch_state WHERE id = 1;
     ```

     Confirm that `updated_at` is within the expected staleness threshold.

4. **Update application configuration**
   - Point the application to the new primary by updating the
     `GEOSYNC_KILL_SWITCH_POSTGRES__DSN` secret or config map. Ensure the TLS
     material referenced by `GEOSYNC_KILL_SWITCH_POSTGRES__TLS__*` matches the
     promoted node.
   - Restart the API pods or trigger a rolling restart so that the connection
     pool reconnects to the new primary.

5. **Verify service health**
   - Observe the readiness endpoint; the `kill_switch` component should return
     to `operational` within the retry budget.
   - Use the administrative API (`GET /admin/kill-switch`) to confirm the
     persisted state matches expectations before resuming trading.

6. **Post-incident actions**
   - Backfill `kill_switch_state` snapshots into long-term storage for audit
     purposes.
   - Review retry and timeout metrics emitted by `PostgresKillSwitchStateStore`
     to tune thresholds if necessary.

## Rollback / Return to Primary

Once the original primary is restored and rejoined the cluster, update the DSN
back to the preferred endpoint and perform a rolling restart. Verify that the
kill-switch state remains consistent before declaring the operation complete.
