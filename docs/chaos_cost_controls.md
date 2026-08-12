# Chaos Resilience and Cost Governance Playbook

This playbook operationalises three priorities raised by the reliability and platform
engineering teams:

1. **Stress containers under CPU, memory, and IO pressure while guaranteeing graceful
   degradation.**
2. **Implement cost attribution and alerting tied to explicit budgets.**
3. **Control expensive research workloads (backtests/benchmarks/features) so they run
   within cost envelopes.**

Each section below defines concrete controls, implementation guidance, and the
associated observability hooks so the programme can be rolled into regular
GameDay, CI, and FinOps cadences.

---

## 1. Container Stress Campaigns with Graceful Degradation

### 1.1 Objectives

- Validate that every critical deployment can sustain sustained CPU, memory, and
  IO pressure without cascading failure.
- Demonstrate automatic fallbacks: traffic shedding, quality-of-service downgrades,
  circuit breakers, and message backlog throttling.
- Produce artefacts (dashboards, logs, postmortems) proving the degradation is
  controlled and reversible.

### 1.2 Test Matrix

| Layer | Stress Tooling | Target Signals | Expected Graceful Behaviour |
| ----- | --------------- | -------------- | --------------------------- |
| **CPU** | `stress-ng --cpu N --cpu-method matrix` injected via ephemeral job in the deployment namespace. | CPU saturation, request latency, queue depth, per-pod throttling. | Autoscaler adds pods up to HPA limit; request router enforces rate limits and downgrades non-critical endpoints; back-pressure metrics stay below 5-minute SLA. |
| **Memory** | `stress-ng --vm N --vm-bytes 80%` or `memhog` with cgroup limits. | Resident set size, OOM kills, cache hit rate. | Process switches to streaming mode (reduced in-memory caching); pod-level eviction triggers readiness probe failure → traffic rerouted; no data loss due to graceful shutdown handlers. |
| **IO / Disk** | `fio` profile with random read/write saturation or throttled PVC bandwidth; `tc` to limit network IO. | Disk latency, fsync duration, Kafka/postgres client latency. | Write queues drain to durable buffer; ingestion switches to capture-only mode; alerts fire when lag > threshold but system stays writable. |

### 1.3 Automation Steps

1. **Define stress jobs** under `deploy/k8s/testing/chaos/` using Helm/Kustomize.
   Parameterise duration, intensity, and target deployment.
2. **Wire into CI Nightlies** via `make chaos-suite` so staging clusters run
   CPU/memory/IO campaigns weekly. Store results in `reports/resilience/stress_*.md`.
3. **Observability hooks**: add synthetic SLO checks (burn rate panels) and
   log markers `degrade_mode=ON|OFF`. Ensure dashboards flag when autoscalers,
   circuit breakers, or feature flags toggle.
4. **Graceful degrade toggles**: document feature flags in `configs/feature_flags.yaml`
   mapping service → degrade strategy (e.g., `execution.partial_fill_mode`).
5. **Recovery validation**: after stress stops, verify metrics return to baseline
   within agreed SLA (e.g., latency P95 < 200ms within 10 minutes). Attach
   Grafana screenshots and Kibana excerpts to the resilience journal.

### 1.4 Exit Criteria

- Each Tier-1 service has a signed-off stress report for CPU, memory, and IO.
- Runbooks in `docs/resilience.md` reference the degrade toggles and rollback
  procedures.
- Degradation behaviour is covered by automated smoke tests (e.g., unit tests that
  assert fallback paths, contract tests verifying throttled responses).

---

## 2. Cost Attribution, Budgets, and Alerting

### 2.1 Tagging & Metadata

1. **Standardise cost tags** (e.g., `env`, `team`, `service`, `strategy`, `job_id`).
   - Extend IaC modules (Terraform/Helm) under `deploy/` to apply tags/labels to
     Kubernetes namespaces, pods, cloud resources, and job queues.
   - Update `observability/prometheus/recording_rules/` to propagate labels into
     metrics (`kube_pod_labels`, `node_namespace_pod_container:container_cpu_usage_seconds_total`).
2. **Backfill historical mapping** by reconciling cluster metadata with billing
   exports. Store lookups in `data/finops/resource_tags.parquet` for auditing.

### 2.2 Budget Definitions

- Maintain budget specs in `configs/budgets/*.yaml` with keys:
  ```yaml
  name: research-cluster
  owner: research@geosync
  monthly_cpu_hours: 1800
  monthly_memory_gb_hours: 5400
  alert_thresholds:
    warn: 0.7
    critical: 0.9
  ```
- Add schema validation via `schemas/budget.json` and enforce through
  `scripts/validate_budgets.py` executed in CI (`make validate-budgets`).

### 2.3 Profiling & Aggregation

1. **CPU-hour counters**: use Prometheus recording rules combining `rate(container_cpu_usage_seconds_total)` with job labels to
   compute `cpu_hours = sum by (job, user) (rate(...) * 1h)`. Persist daily
   snapshots to ClickHouse or BigQuery via the existing observability pipeline.
2. **Memory GB-hour counters**: integrate `container_memory_usage_bytes`
   metrics, convert to GB, and aggregate by job/user. Apply exponential moving
   averages to smooth spikes.
3. **Per-job profiling**: extend the job scheduler (e.g., Airflow, Argo Workflows)
   to emit structured events (`job_started`, `job_completed`) with resource
   requests/limits and actual usage. Feed events to the FinOps warehouse for
   reconciliation.

### 2.4 Alerting & Reporting

- Configure Alertmanager rules so when spend ratio exceeds thresholds:
  - **Warn**: route to owning team Slack channel with guidance (pause low-priority
    jobs, clean up idle clusters).
  - **Critical**: page FinOps on-call and auto-apply guardrails (reduce max
    concurrency, freeze new ad-hoc runs).
- Publish weekly FinOps dashboards combining cost burn, budget utilisation,
  and forecasted month-end spend.
- Add monthly review checklist to `reports/finops/budget_review.md` capturing
  decisions, exceptions, and remediation tasks.

---

## 3. Research Workload Cost Controls

### 3.1 Heavy Backtest Governance

1. **Job Classification**
   - Annotate backtest configurations with `workload_tier` (e.g., `interactive`,
     `batch`, `nightly`). Store in `configs/backtest/*.yaml` and enforce via
     schema validator.
   - Extend `geosync_cli backtest` to reject `workload_tier: heavy` submissions
     outside scheduled windows unless override flag `--force-heavy` is provided
     by authorised users.
2. **Scheduler Integration**
   - Use the workflow orchestrator to gate heavy runs: create a cron-triggered
     nightly window where `heavy` jobs are queued. Outside the window, they are
     paused or rescheduled.
   - Maintain audit log `reports/backtest/heavy_job_denials.csv` for transparency.

### 3.2 Benchmark & Feature Cache

- **Benchmark caching**: persist benchmark artefacts (e.g., `pytest-benchmark`
  JSON, profiling flamegraphs) under `bench/artifacts/` keyed by git SHA. Provide
  CLI command `geosync_cli bench --use-cache` to reuse results when code
  paths are unchanged.
- **Feature store caching**: integrate with the Feature Catalog so feature
  computations store hashed inputs/output metadata. When identical parameters are
  requested, return cached dataset instead of recomputing.
- **Invalidation**: tie cache invalidation to schema/version changes. Document
  policies in `docs/feature_store.md`.

### 3.3 Cost-Aware Defaults

- Default CLI flags to conservative resource usage (`--max-workers`, `--sample-rate`).
- Provide `make research-budget-check` target running quick estimations of
  expected CPU/memory hours before launching runs.
- Document "frugal research" guidelines in onboarding materials so analysts know
  when to request overrides.

### 3.4 Success Metrics

- ≥20% reduction in off-hours compute spend for research clusters within two
  quarters.
- Zero unplanned heavy backtests during trading hours.
- Cache hit rate ≥70% for repeated benchmark/feature jobs.

---

## Operationalisation Checklist

- [ ] Chaos suite definitions merged and scheduled.
- [ ] Budget configs validated and alerting live in staging.
- [ ] Backtest gating and caching deployed with audit trail in place.
- [ ] Monthly review cycle logs actions and KPIs in FinOps dashboard.

Review this playbook quarterly with SRE + FinOps + Research leads and update the
checklist to reflect newly automated controls or additional safeguards.
