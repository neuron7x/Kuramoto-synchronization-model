# Deployment Guide

This guide outlines the production deployment requirements for GeoSync, including infrastructure, secret management, and operation of the live trading runner. It complements the [Production Cutover Readiness Checklist](../reports/prod_cutover_readiness_checklist.md).

## Infrastructure Requirements

| Component | Purpose | Recommended Baseline |
|-----------|---------|----------------------|
| **PostgreSQL 15+** | Stores strategy state, OMS snapshots, and execution audit trails. | Highly available cluster (e.g., managed Postgres, Patroni) with point-in-time recovery enabled. |
| **Kafka 3.5+** (or compatible message bus) | Distributes ticks, signals, and order events between ingestion, strategy, and execution services. | Three-broker cluster with replication factor ≥ 3, rack-aware placement, and topic-level ACLs. |
| **Prometheus + Alertmanager** | Scrapes metrics from GeoSync services, including the live trading loop heartbeat. | Dedicated metrics namespace with 15 s scrape interval and long-term storage via Thanos or Cortex. |
| **Object storage (S3/GCS/MinIO)** | Optional for historical data snapshots and strategy artifacts. | Versioned bucket with lifecycle policies to control retention. |
| **Secrets backend (Vault, AWS Secrets Manager, GCP Secret Manager)** | Centralised distribution of exchange credentials and API tokens. | Configure per-environment namespaces and audit logging. |

### Networking & Security

Refer to the [Production Security Architecture](security/architecture.md) for a
full description of the edge, DMZ, and core tiers, including the logging and
identity requirements that underpin these controls.

- Restrict inbound access to OMS and connector hosts using security groups or firewall rules.
- Enforce mTLS between strategy services and Kafka/Postgres where supported (see the [Zero Trust Service Mesh Runbook](security/zero_trust_runbook.md) for mesh identities and policy templates).
- Mirror Prometheus metrics to your SIEM for long-term incident investigations.

### Kafka Broker Security Configuration

- GeoSync expects Kafka clusters to expose TLS endpoints (`security_protocol` of `SSL` or `SASL_SSL`). Provide the CA bundle path via `EventBusConfig.ssl_cafile` and, when using mutual TLS, supply the signed client certificate and key files.
- Rotate broker and client certificates on a fixed cadence (e.g., quarterly). Deploy new files alongside the old ones, then restart services to reload credentials before revoking the previous certificates.
- When SASL is enabled, configure ACLs per topic and per consumer group. Bind the SASL principal used by GeoSync to the event topics defined in `core/messaging/event_bus.py` and deny wild-card access to minimise blast radius.
- Document the certificate and ACL owners in your runbooks so incident responders know who to contact when a rotation or ACL change is required.

## Secret Management Expectations

GeoSync loads sensitive credentials exclusively from environment variables or injected secret files.

1. **Source of truth** – Store live venue keys in your secret manager; do not commit them to Git.
2. **Rotation** – Align key rotation policies with venue requirements. The live trading loop supports hot credential reloads when files in the `state_dir` change.
3. **Distribution** – Inject credentials during deployment (e.g., Kubernetes secrets, HashiCorp Vault Agent) and expose them as environment variables such as `BINANCE_API_KEY` and `COINBASE_API_SECRET` as documented in [Configuration](configuration.md#exchange-connector-credentials).
4. **Audit** – Enable secret manager audit trails and configure alerts for unusual access patterns.

## Horizontal Pod Autoscaling

The `geosync-api` deployment now ships with a production-grade Horizontal Pod Autoscaler (HPA) defined in
[`deploy/kustomize/base/hpa.yaml`](../deploy/kustomize/base/hpa.yaml). The controller uses multiple signals to balance
latency SLOs against compute cost:

- **CPU utilisation**: target 60% average utilisation across pods. This keeps per-core headroom for GC pauses and order routing bursts.
- **Memory utilisation**: target 70% average utilisation to guard against Python heap growth while avoiding premature scale-out.
- **Signal-to-fill latency (p95)**: pods metric filtered on `quantile="0.95"` with a 400 ms target. Breaches indicate exchange latency or strategy slowdowns that demand extra workers.
- **Order queue depth**: external Prometheus metric `geosync_orders_queue_depth` with a target value of 80 messages. This prevents cascading backlog when upstream venues throttle.

### Anti-spike behaviour

To prevent thrashing during volatile market windows the HPA enforces aggressive dampening:

- Scale-up requests are stabilised for 60 seconds (45 seconds in staging) with pod and percentage policies to cap surges at +4 pods/min in base and +6 pods/min in production.
- Scale-down requests are stabilised for five minutes (three minutes in staging) and limited to two pods or 30% per window in base. Production is even more conservative (max three pods or 20% per window) to avoid brown-outs during partial market recoveries.
- Environment overlays adjust the replica floor/ceiling: staging runs between 2–6 pods for cost control, production between 6–24 to absorb exchange-driven cascades.

### Load and cascade validation

1. **Apply the overlay**:
   ```bash
   kubectl apply -k deploy/kustomize/overlays/<environment>
   ```
2. **Generate synthetic load** with k6 using the maintained scenario in [`deploy/loadtests/hpa-k6.js`](../deploy/loadtests/hpa-k6.js):
   ```bash
   k6 run \
     --env GEOSYNC_BASE_URL="http://geosync-api.geosync-<environment>.svc.cluster.local" \
     --env GEOSYNC_LATENCY_SLO_MS=400 \
     deploy/loadtests/hpa-k6.js
   ```
   Run the scenario for at least 15 minutes so that all HPA policies trigger.
3. **Backlog drill**: follow the procedure in [Queue and Backpressure](queue_and_backpressure.md) to temporarily throttle order consumers and drive `geosync_orders_queue_depth` above 80. Observe the queue depth and latency metrics in Grafana.
4. **Validate scaling**:
   ```bash
   kubectl get hpa geosync-api --watch
   ```
   Confirm replica counts climb smoothly without exceeding policy caps, then decay only after queue depth and latency recover.
5. **Document results** in the runbook, capturing replica timelines, latency plots, and queue depth recovery to prove resilience under cascading peaks.

The administrative FastAPI surface consumes the `GEOSYNC_AUDIT_SECRET` via a managed file watcher that honours rotations at runtime. When you mount `GEOSYNC_AUDIT_SECRET_PATH` (and, optionally, `GEOSYNC_SIEM_CLIENT_SECRET_PATH`) into the container, the service refreshes the keys according to `GEOSYNC_SECRET_REFRESH_INTERVAL_SECONDS` without restarts. Ensure your secret manager agent keeps the files up to date and enforces length policies that satisfy the defaults (16+ characters for audit signatures).

## Configuring the Live Trading Runner

The live runner is implemented in [`execution/live_loop.py`](../execution/live_loop.py) and orchestrates connectors, the order management system, and risk controls.

1. **Prepare the state directory** – Mount a persistent volume for the runner and point `LiveLoopConfig.state_dir` to it. Each venue will receive a `${venue}_oms.json` snapshot used for reconciliation.
2. **Supply credentials** – Provide a mapping of venue names to API keys when creating `LiveLoopConfig(credentials=...)`. If you rely on environment variables only, leave the mapping empty and let connectors pull from the process environment.
3. **Bootstrap connectors** – Instantiate `ExecutionConnector` implementations for every venue you intend to trade. Ensure that WebSocket endpoints and REST base URLs are configured for the production environment.
4. **Risk management** – Construct a `RiskManager` with the relevant guards (position limits, P&L circuit breakers, kill switches). The live runner emits lifecycle events via `on_kill_switch`, `on_reconnect`, and `on_position_snapshot` signals—subscribe automation to these hooks for observability and fail-safes.
5. **Start the loop** – Call `LiveExecutionLoop.start(cold_start=False)` during deployment. Use `cold_start=True` only for the first cutover to avoid reusing stale state.
6. **Monitoring** – Scrape the metrics collector referenced by the loop (see `core.utils.metrics`). Ensure the following series are present: `live_loop_heartbeat`, `live_loop_orders_submitted_total`, and `live_loop_position_snapshot_timestamp`.
7. **Kill switch drills** – Schedule quarterly tests where the kill switch is triggered and verify that connectors disconnect, metrics report the event, and PagerDuty receives notifications.

## Configuration Promotion Workflow

1. Stage configuration changes in `configs/` and validate using paper trading or sandbox credentials.
2. Use the `reports/release_readiness.md` template to capture sign-off from risk and platform engineering.
3. For Kubernetes deployments, package configs as ConfigMaps with versioned labels; for VM-based deployments, store them in GitOps repositories and roll out via Ansible or Terraform.
4. Always run the regression test suite (`make test`) before promoting a build.

## Rollback Procedures

GeoSync rollbacks tie directly to the [Production Cutover Readiness Checklist](../reports/prod_cutover_readiness_checklist.md):

1. **Trigger conditions** – Monitor the SLO guardrails defined in the checklist (error rate > 2%, p95 latency > 500 ms, or metric gaps). When a breach occurs, the AutoRollbackGuard should emit the rollback callback.
2. **Execution** – Stop the live runner (`LiveExecutionLoop.shutdown()`), scale down new versions, and redeploy the previous tagged release from your artifact registry.
3. **Data reconciliation** – Restore OMS snapshots from the `state_dir` backups. Validate Postgres replicas and Kafka offsets against the pre-cutover baseline.
4. **Verification** – Re-run the checklist items marked as rollback drills to confirm the environment returned to nominal state.
5. **Postmortem** – File an incident report and attach telemetry exports (Prometheus, logs, Kafka lag metrics) for root-cause analysis.

## Troubleshooting Deployment Issues

- **Kafka consumer lag** – Inspect topic consumer groups and ensure partitions are balanced. If lag persists, scale execution workers horizontally.
- **Prometheus scrape failures** – Confirm service discovery labels include the live runner endpoints and TLS certificates are valid.
- **State reconciliation loops** – Remove corrupted OMS snapshots and restart with `cold_start=True`; the loop will regenerate clean state from the venues.
- **Credential mismatches** – Rotate secrets in the manager and restart pods to pick up the new values. Subscribe to the `on_kill_switch` signal to ensure trading halts during mismatches.

For additional operational policies, refer to [`docs/operational_readiness_runbooks.md`](operational_readiness_runbooks.md) and [`docs/incident_playbooks.md`](incident_playbooks.md).
