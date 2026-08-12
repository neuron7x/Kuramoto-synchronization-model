# Zero Trust Service Mesh Runbook

This runbook defines the operational guide for enforcing zero trust networking across GeoSync services using an Istio-based service mesh. It covers workload identities, certificate authority integration, intent-based authorization, observability hooks, and incident response.

## Architecture Overview

- **Service mesh** – Istio provides multi-cluster capability, SPIFFE-compliant workload identities, and sidecarless ambient mode for latency-sensitive execution services. The mesh controls east-west traffic for ingestion, strategy, execution, and UI workloads alongside shared infrastructure such as the metrics exporters described in `observability/exporters.py`.
- **Control plane** – The Istio control plane (istiod) runs in a hardened `mesh-system` namespace with restricted RBAC. Configuration is managed via GitOps, mirroring the broader configuration approach documented in [`docs/deployment.md`](../deployment.md).
- **Data plane** – Sidecars (or ambient ztunnel/waypoint proxies) are injected into Kubernetes namespaces matching GeoSync components. Injection is toggled through namespace labels so batch jobs (e.g., backtests) can opt-in when they expose HTTP/gRPC APIs.

## SPIFFE Identity Schema

All workloads obtain SPIFFE identities from the mesh using the following schema:

```
spiffe://geosync/<environment>/<service>[/<workload>]
```

- `<environment>` – `dev`, `staging`, or `prod` to match the deployment environments referenced in [`observability/tracing.py`](../../observability/tracing.py) resource attributes.
- `<service>` – Logical service families tied to repository paths:
  - `ingestion` → data ingest processes in `core` and `markets` packages responsible for populating feature stores.
  - `strategy` → research and optimisation workers located in `analytics` and `backtest` modules.
  - `execution` → live trading runners and OMS integrations under `execution/` with runtime configs in [`configs/live/default.toml`](../../configs/live/default.toml).
  - `ui` → analyst web front-end hosted in [`apps/web`](../../apps/web).
  - `observability` → telemetry collectors defined in [`observability/`](../../observability/README.md).
- `<workload>` – Optional workload qualifier for multi-tenant pods (e.g., `strategy/optimizer` vs `strategy/backtester`).

### Identity issuance flow

1. Namespace admission controller injects Istio sidecar and annotates pod with workload metadata.
2. Workload presents Kubernetes service account JWT to Istio’s SDS server.
3. Istio mints an X.509 certificate with the SPIFFE URI SAN above and pushes it to the sidecar via SDS.
4. Sidecar exposes the certificate to the application through in-memory secrets; applications connect using TLS and trust the shared CA bundle.

## Certificate Authority Integration

- **Root of trust** – A corporate PKI root issues an intermediate certificate dedicated to the mesh. The intermediate certificate is imported into Istio’s MeshConfig as an external CA, allowing certificate chaining back to the organisation-wide trust store.
- **Rotation cadence** – Intermediate certificates rotate annually, with overlapping validity to avoid downtime. Workload certificates rotate every 12 hours by default, matching Istio’s recommended TTL.
- **Bootstrap process**:
  1. Generate CSR from the Istio mesh CA service.
  2. Sign the CSR with the corporate intermediate and upload the signed cert and key to Kubernetes as `istio-ca-secret`.
  3. Reload istiod pods so the new certificate takes effect.
  4. Validate that workloads receive new certificates via `istioctl proxy-config secret`.

## Policy Mapping to GeoSync Services

| Service family | Repository scope | Allowed mesh intents | Denied intents |
| -------------- | ---------------- | -------------------- | -------------- |
| Ingestion | `core/`, `markets/` | Call `strategy` APIs to publish features; push metrics to `observability` endpoints defined in [`observability/metrics.json`](../../observability/metrics.json). | Direct calls to `execution` order submission paths; internet egress except through approved egress gateways. |
| Strategy | `analytics/`, `backtest/`, `apps/web` background jobs | Read from `ingestion`; call `execution` quote services for paper trading; access feature store caches. | Write access to live execution order endpoints; unauthenticated internet egress. |
| Execution | `execution/`, configs in [`configs/live/default.toml`](../../configs/live/default.toml) | Accept traffic from authorised `strategy` identities; call exchange gateways and telemetry sinks. | Any direct requests from `ui`; unsolicited calls to `ingestion` services. |
| UI & APIs | [`apps/web`](../../apps/web) | Query `strategy` and `observability` APIs via mesh gateway. | Direct calls to `execution` OMS; access to raw ingestion streams. |
| Observability | [`observability/`](../../observability/README.md) | Scrape metrics from all namespaces; receive tracing spans (see [`observability/tracing.py`](../../observability/tracing.py)). | Initiate order or data plane calls; mutate business services. |

Policies are codified as AuthorizationPolicy CRDs bound to the SPIFFE IDs above. Changes follow the same review rigor as other configuration artefacts, requiring approvals before merge.

## Operational Procedures

### Onboarding a New Service Identity

1. **Designate namespace and service account** – Create (or reuse) a Kubernetes namespace and service account for the workload. Label the namespace with `istio-injection=enabled`.
2. **Define SPIFFE attributes** – Choose `<service>` and optional `<workload>` segments matching the scope guidelines.
3. **Provision policy** – Add a ServiceEntry and AuthorizationPolicy in the GitOps repo allowing only the required intents (e.g., `strategy` → `execution`).
4. **Update configuration templates** – Extend Helm/manifest templates or config files (e.g., [`configs/templates/exec.yaml.j2`](../../configs/templates/exec.yaml.j2)) with the service account annotations.
5. **Deploy and verify** – Roll out the workload, then validate identity issuance with `istioctl x workload entry configure` or `kubectl exec` to inspect `/etc/certs` for the SPIFFE SAN.
6. **Register observability** – Update the metrics catalogue or alerts if the service exports new telemetry, following the workflow in [`observability/README.md`](../../observability/README.md).

### Rotating Mesh Certificates

1. **Plan the window** – Schedule rotation within the annual CA overlap. Notify stakeholders via the change calendar.
2. **Prepare new intermediate** – Obtain the signed intermediate bundle from PKI and store it in secrets management (see [`docs/deployment.md`](../deployment.md) secret management expectations).
3. **Update Istio secret** – Patch `istio-ca-secret` with the new certificate and key.
4. **Restart control plane** – Sequentially restart istiod pods to load the new credentials.
5. **Force workload refresh** – Optionally trigger `kubectl rollout restart` on critical deployments (execution, ingestion) to minimise overlap with expiring certs.
6. **Validate** – Run `istioctl proxy-config secret <pod>` to confirm new expiration dates.
7. **Audit** – Archive rotation evidence and certificate fingerprints alongside governance artefacts in accordance with [`docs/governance.md`](../governance.md).

### Enforcing Intent-Based Authorization

1. **Model intents** – Define allowed caller → callee pairs referencing the policy matrix above.
2. **Author policies** – Create AuthorizationPolicy resources mapping SPIFFE principals to destination workloads. Require mutual TLS mode `STRICT` in DestinationRules.
3. **Integrate with application config** – Ensure services only advertise endpoints behind mesh addresses (e.g., `strategy.mesh.svc.cluster.local`). Execution configs in [`configs/live/default.toml`](../../configs/live/default.toml) should point to the mesh service names.
4. **Test** – Use `istioctl x authz check` to validate policy decisions before deployment.
5. **Continuous validation** – Incorporate conftest or OPA checks in CI to ensure new policies do not widen access unexpectedly.

### Monitoring Policy Violations

- **Prometheus alerts** – Extend `observability/alerts.json` with rules tracking `istio_requests_total{response_code="403"}` spikes for mesh-denied requests.
- **Metrics dashboards** – Update Grafana dashboards under `observability/dashboards/` to visualise mTLS handshake errors and identity issuance latency.
- **Tracing** – Propagate mesh IDs via OpenTelemetry instrumentation in [`observability/tracing.py`](../../observability/tracing.py) to correlate denied requests with calling workloads.
- **Audit logs** – Enable Istio audit logging and stream events to the SIEM alongside application telemetry described in [`observability/README.md`](../../observability/README.md).

## Troubleshooting and Incident Response

Mesh-related outages follow the broader incident process described in [`docs/incident_playbooks.md`](../incident_playbooks.md):

1. **Detection** – Mesh policy violations or certificate expirations typically surface as elevated 403/503 rates or connectivity drops. Alerts added to `observability/alerts.json` should page the appropriate team.
2. **Stabilise** – Apply circuit-breaker actions similar to the execution lag playbook by reducing strategy fan-out or routing traffic through healthy waypoints while policies are corrected.
3. **Diagnose** – Compare recent mesh configuration commits, inspect `istioctl analyze` output, and capture failing requests with `istioctl proxy-config log`.
4. **Mitigate** – Temporarily grant scoped emergency access via short-lived AuthorizationPolicy overrides, recording each change for post-incident review.
5. **Recover** – Revert overrides, rotate impacted certificates if compromise is suspected, and validate that workloads resume normal telemetry baselines.
6. **Postmortem** – Submit findings to the governance council referencing control objectives in [`docs/governance.md`](../governance.md) and update this runbook with lessons learned.

## References

- [`docs/governance.md`](../governance.md) – Access policy governance and review cadence.
- [`docs/deployment.md`](../deployment.md) – Deployment expectations, including secret rotation practices.
- [`docs/incident_playbooks.md`](../incident_playbooks.md) – Primary incident response playbooks for GeoSync.
- [`observability/`](../../observability/README.md) – Telemetry catalogue, alerting rules, and tracing helpers leveraged by the mesh.
