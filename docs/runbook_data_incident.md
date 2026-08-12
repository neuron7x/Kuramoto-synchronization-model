# Runbook: Market Data Incident Response

This runbook defines the coordinated steps required to recover from market data
incidents such as ingestion stalls, corrupted payloads, or delayed vendor
updates.

## 1. Detection and Triage

1. **Trigger sources** – Automated alerts from ingestion lag dashboards,
   checksum failures, schema mismatches, or user reports.
2. **Confirm scope** – Identify affected venues, symbols, and time ranges using
   the metadata store (`observability/catalog/data_health`).
3. **Stabilise pipelines** – Pause downstream consumers (feature store writers,
   backtest exporters) via control plane toggles to prevent propagation.
4. **Create incident ticket** – Open a PagerDuty bridge and log the incident in
   `reports/incidents/data/<date>-<id>/timeline.md`, використовуючи шаблон
   [`reports/incidents/incident_report_template.md`](templates/incident_playbook.md)
   для структурування запису.

## 2. Containment Actions

- **Freeze strategy updates** – Halt live strategy promotions touching impacted
  feeds. Notify the live-trading team to evaluate kill-switch posture.
- **Quarantine data** – Redirect offending batches into a quarantine bucket
  (`s3://geosync-data/quarantine/`) tagged with incident ID.
- **Vendor liaison** – Engage vendor support; capture reference numbers in the
  incident timeline.

## 3. Recovery Workflow

### 3.1 Restore Ingestion

1. Validate upstream connectivity (network checks, authentication tokens).
2. Re-seed connectors using `python cli/ingestion.py --reseed --market <id>`.
3. Monitor ingestion lag metrics until they fall below SLA (<60 seconds for
   streaming, <5 minutes for batch).
4. Record restart confirmation in `observability/audit/ingestion_events.jsonl`.

### 3.2 Backfill Missing Data

1. Determine gap windows via `data quality` dashboards or `reports/incidents/.../gap.csv`.
2. Launch backfill job:
   ```bash
   geosync-cli ingest backfill --market <id> --start <iso> --end <iso> \
       --output reports/backfill/<incident_id>/
   ```
3. Validate row counts against vendor totals and checksum manifests.
4. Promote backfilled data to staging tables, then to production after validation.

### 3.3 Re-Validate Data Quality

1. Run automated quality suite: `pytest tests/data_quality/ -k "market_calendar"`.
2. Trigger DST/holiday edge-case tests to confirm calendar alignment (see
   [Quality Gates](quality_gates.md)).
3. Execute comparative indicator checks to ensure derived features (Kuramoto,
   Ricci, Hurst) match pre-incident baselines within tolerances.
4. Update the incident dashboard with validation status and attach artefacts.
5. Перенесіть чернетку постмортему в
   [`reports/incidents/postmortem_template.md`](POSTMORTEM_TEMPLATE.md)
   відразу після стабілізації сервісу, щоб не втратити деталі.

## 4. Communication Plan

| Stage | Audience | Channel | Message |
| ----- | -------- | ------- | ------- |
| Detection | Trading Ops, Risk, Quant On Call | PagerDuty bridge + `#incidents` | `Data incident <id> detected, markets impacted: <list>` |
| Containment | Executives, Compliance | Email + `#leadership-tech` | `Ingestion paused for <markets>, ETA <time>` |
| Recovery start | Trading Ops | `#trading-ops` | `Backfill initiated for <markets> covering <range>` |
| Validation pass | Trading Ops, Risk, Compliance | `#trading-ops` + status page | `Data restored and validated, resuming normal ops` |
| Post-mortem ready | Org-wide | Confluence | `Incident <id> retrospective published` |

## 5. Exit Criteria

- Ingestion pipelines stable for 2x SLA window.
- Backfills applied and reconciled with vendor totals.
- Automated quality suite (including DST/session boundary tests) green.
- Strategy teams sign off that derived signals fall within expected tolerances.
- Incident ticket resolved with root cause, actions, and owners captured.

## 6. Preventive Follow-Up

1. File defects for tooling or observability gaps discovered.
2. Update monitoring thresholds or add new detectors if incident evaded prior
   alerts.
3. Schedule chaos replay (simulate similar fault) within 30 days.
4. Refresh runbook and linked dashboards with learnings.

Keeping this runbook accurate is mandatory; review after each data incident and
quarterly during governance audits.
