# Operational Excellence Handbook

This handbook consolidates the operational artefacts that keep GeoSync
reliable, reproducible, and auditable. Each section links to the authoritative
runbooks, test suites, and governance controls maintained in the repository so
teams can reach production readiness without tribal knowledge.

## Runbooks, Releases, and On-Call Discipline

- **Incident response** – Follow the playbooks for execution outages,
  rejections, and data gaps documented in
  [`docs/incident_playbooks.md`](incident_playbooks.md). The dedicated data
  incident workflow covers triage, containment, and validation in
  [`docs/runbook_data_incident.md`](runbook_data_incident.md), while
  [`docs/runbook_live_trading.md`](runbook_live_trading.md) handles live strategy
  escalations.
- **Regional disasters** – Activate the
  [`docs/runbook_disaster_recovery.md`](runbook_disaster_recovery.md) plan to
  promote standby regions, validate RPO/RTO adherence, and maintain regulatory
  audit trails when a site is impaired or destroyed.
- **Release gates** – Each deployment must complete the readiness checklist in
  [`reports/release_readiness.md`](../reports/release_readiness.md) alongside the
  production cutover template
  [`reports/prod_cutover_readiness_checklist.md`](../reports/prod_cutover_readiness_checklist.md).
- **Operational alignment** – The consolidated control tower in
  [`docs/operational_readiness_runbooks.md`](operational_readiness_runbooks.md)
  maps approvals, start/stop scripts, SLA monitors, and archival checklists so
  live sessions stay audit-grade.
  These artefacts ensure cutovers include go/no-go evidence, telemetry sign-off,
  and rollback criteria.
- **On-call routine** – The escalation policy, error budget tracking, and SLO
  drill cadence live in [`docs/reliability.md`](reliability.md). Combine those
  policies with the communications plan embedded in the runbooks above to keep
  incidents contained and retrospectives complete.
- **Time synchronisation** – Follow the dedicated NTP/PTP playbook in
  [`docs/runbook_time_synchronization.md`](runbook_time_synchronization.md) to
  monitor drift, enforce automated remediation, and keep event timestamps
  audit-grade across trading surfaces.

## Golden Data and Quality Playbooks

- **Data backstops** – The data runbook prescribes quarantine buckets,
  backfills, and quality validation suites when ingest feeds misbehave, forming
  the "golden data" pathway for regulated markets
  [`docs/runbook_data_incident.md`](runbook_data_incident.md).
- **Indicator MACD baseline** – `data/golden/indicator_macd_baseline.csv`
  provides a five-row canonical dataset with pre-computed MACD components,
  including the histogram, so
  regressions can compare indicator outputs deterministically. The defaults
  `(12, 26, 9)` mirror `FeaturePipelineConfig`'s `macd_fast`, `macd_slow`, and
  `macd_signal` parameters to keep regression harnesses aligned with the live
  feature pipeline.
- **Quality gates** – Enforce code, test, and performance standards by adopting
  the gating catalogue in [`docs/quality_gates.md`](quality_gates.md), which
  pairs coverage, regression budgets, and break-glass expectations with CI
  automation.
- **Stress campaigns** – Resilience and chaos drills for extreme market states
  are defined in [`docs/stress_playbooks.md`](stress_playbooks.md), ensuring data
  freshness and signal integrity stay inside tolerance bands during turbulence.

## Reproducible End-to-End Examples

- **Notebooks** – The comprehensive tutorial notebook
  [`docs/notebooks/complete_tutorial.ipynb`](notebooks/complete_tutorial.ipynb)
  demonstrates ingestion, feature building, model training, backtesting, and
  reporting with deterministic seeds.
- **Frozen clocks** – Tests and smoke scripts can call
  `core.utils.freeze_time` to pin wall-clock and monotonic timers, eliminating
  time-sensitive flakes during reproducibility checks.
- **Example gallery** – Developers can execute runnable workflows from
  [`docs/examples/README.md`](examples/README.md) and the scripts under
  [`examples/`](../examples/). Performance demos and indicator profiles rely on
  fixed RNG seeds (for example `np.random.default_rng(7)` in
  [`bench/bench_indicators.py`](../bench/bench_indicators.py)) so reports stay
  comparable across runs.
- **Snapshot data** – Sample OHLC datasets ship under `data/` to remove external
  dependencies for tutorials and CI smoke runs (`data/sample.csv`,
  `data/sample_ohlc.csv`).

## Performance Budgets and Regression Harnesses

- **Microbenchmarks** – Use the indicator and pipeline harnesses in
  [`bench/`](../bench/) together with the optimisation recipes documented in
  [`docs/performance.md`](performance.md) to track cold-start versus hot-loop
  timing.
- **Automated budgets** – Extend the guidance in
  [`docs/performance.md`](performance.md) to wire `pytest-benchmark` and Airspeed
  Velocity runs into CI. Profiling traces from `pytest-profiling` are already
  archived by the workflow in
  [`.github/workflows/tests.yml`](../.github/workflows/component-test-router.yml) for regression
  triage.

## Data Lake Lifecycle (Iceberg and Delta)

- **Source of truth** – Feature stores can materialise from Delta Lake or Apache
  Iceberg tables through the offline adapters defined in
  [`core/data/feature_store.py`](../core/data/feature_store.py). The architecture
  blueprint outlines partitioning by symbol/date and validation workflows in
  [`docs/architecture/feature_store.md`](architecture/feature_store.md).
- **Maintenance tasks** – Schedule compaction, vacuum, and Z-ordering passes as
  part of the nightly maintenance window so offline tables stay performant
  before syncing to the online store. Pair these jobs with the retention policies
  inside the feature store module to prevent stale partitions from lingering.

## Online Feature Store Security Controls

- **Redis TLS and ACLs** – The `RedisOnlineFeatureStore` now enforces TLS for all
  connections. Operators must provision `rediss://` endpoints or inject a
  pre-configured SSL context when instantiating the store. Grant the Redis ACL
  user only `GET`, `SET`, `DEL`, `PEXPIRE`, and `PTTL` permissions; append-only
  commands (`APPEND`, scripting, or `KEYS`) remain prohibited. The TLS
  certificate bundle should be rotated alongside the ACL password on a
  quarterly cadence, ensuring cached credential material in the services is
  refreshed via rolling restarts.
- **SQLite encryption keys** – The `SQLiteOnlineFeatureStore` now requires
  explicit encryption keys and refuses to start without them. Store teams must
  supply unique `key_id` identifiers for each deployment and rotate the primary
  key by updating the configuration and invoking
  `core.data.feature_store.reencrypt_sqlite_payloads` with the previous key as a
  fallback. This migration rewraps all payloads in AES-GCM envelopes and can
  execute in place after a filesystem snapshot is taken. Retain the prior key
  in the configuration’s `fallback_keys` map for at least one release cycle to
  allow blue/green deploys to read data materialised with the previous key.

## Arrow/Parquet Caching Strategy

- **Indicator cache** – `FileSystemIndicatorCache` persists feature batches to
  Parquet/Numpy assets with deterministic fingerprints and metadata, ensuring
  warm-up times stay predictable across deployments
  [`core/indicators/cache.py`](../core/indicators/cache.py).
- **Layered ingestion cache** – The backfill registry caches raw, OHLCV, and
  derived frames with explicit coverage windows, enabling TTL-style eviction and
  targeted invalidation per market regime
  [`core/data/backfill.py`](../core/data/backfill.py).
- **Warm-up guidance** – Prime frequently requested views after deploys by
  replaying the cached coverage intervals; the caches record timestamps and
  fingerprints so operators know when re-materialisation is necessary.

## Quality Gates and Break-Glass Controls

- **Pre-commit hooks** – Ruff, Black, MyPy, Detect-Secrets, and Slotscheck run
  via the shared configuration in [`.pre-commit-config.yaml`](../.pre-commit-config.yaml)
  with dependencies pinned in [`requirements-dev.txt`](../requirements-dev.txt)
  to prevent drift.
- **Escalation** – The break-glass checklist is documented inside
  [`docs/quality_gates.md`](quality_gates.md), which ties emergency merges to
  follow-up retrospectives and governance actions.

## Property- and Fuzz-Testing Playbooks

- **Property suites** – Hypothesis-based generators cover indicator stability,
  execution invariants, and schema contracts throughout `tests/property/`, for
  example the backtest invariants in
  [`tests/property/test_backtest_properties.py`](../tests/property/test_backtest_properties.py).
- **Fuzz harnesses** – Randomised payloads ensure ingestion adapters and
  execution connectors remain defensive under malformed input in
  [`tests/fuzz/test_ingestion_fuzz.py`](../tests/fuzz/test_ingestion_fuzz.py).
  Consult [`TESTING.md`](operations/TESTING.md) for commands that aggregate property and
  fuzz statistics in CI.

## Compatibility Matrix and Fallback Paths

- **Python matrix** – CI exercises Python 3.11, 3.12, and 3.13 via the matrix in
  [`.github/workflows/tests.yml`](../.github/workflows/component-test-router.yml) to guarantee
  forward compatibility before releases.
- **GPU fallbacks** – Indicator kernels automatically downgrade to CPU when CuPy
  is unavailable, with explicit tests covering both code paths in
  [`tests/unit/indicators/test_kuramoto_fallbacks.py`](../tests/unit/indicators/test_kuramoto_fallbacks.py)
  and the adaptive entropy backend selection in
  [`core/indicators/entropy.py`](../core/indicators/entropy.py).
- **Distribution targets** – The wheel pipeline in
  [`.github/workflows/build-wheels.yml`](../.github/workflows/wheel-contract-gate.yml)
  packages manylinux and musllinux wheels so downstream systems can install on
  glibc- and musl-based distributions without manual rebuilding.

## Governance and GitHub Controls

- **CODEOWNERS and reviews** – Mandatory reviewers are enforced through
  [`.github/CODEOWNERS`](../.github/CODEOWNERS) and the pull request template in
  [`.github/pull_request_template.md`](../.github/pull_request_template.md), which
  includes documentation, telemetry, and risk checklists.
- **Security policy** – Coordinated disclosure expectations, contact channels,
  and supported version commitments are centralised in [`SECURITY.md`](../SECURITY.md).
- **Version policy** – Release cadence, compatibility guarantees, and lifecycle
  obligations are tracked through [`VERSION`](../VERSION) and the roadmap
  artefacts referenced from [`docs/index.md`](index.md).

Keep this handbook in sync with production practices: update links when runbooks
change, summarise new CI guardrails, and ensure every operational discipline has
an explicit owner and review cadence.
