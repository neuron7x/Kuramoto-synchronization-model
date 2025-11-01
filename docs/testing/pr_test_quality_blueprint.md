# TradePulse Pull Request Test Reinforcement Blueprint

This blueprint consolidates the current TradePulse quality signal coverage, highlights the existing release gates, and enumerates the steps required to align pull-request validation with the thermodynamic and regulatory invariants mandated for TACL.

## 1. Repository-wide test inventory

### 1.1 Python test suites (pytest)

| Suite | Location | Focus | Notes |
| --- | --- | --- | --- |
| Full analytics pipeline regression | `tests/e2e/test_full_pipeline.py` | Synthetic ingest → feature engineering → strategy backtest → reporting, exercises CLI, report renderers, and PDF artifacts. | Provides p95 guardrails for report generation and ensures CLI surfaces remain consistent for downstream integrations.【F:tests/e2e/test_full_pipeline.py†L1-L132】
| Live trading loop regression | `tests/e2e/test_trading_cycle.py` | Exercises TradePulseSystem ingest, signal generation, OMS integration, and risk ledger reconciliation on sandbox market data. | Validates DTO serialization, order lifecycle, and risk invariants for BTCUSDT path.【F:tests/e2e/test_trading_cycle.py†L1-L116】
| Progressive rollout guard | `tests/e2e/test_progressive_rollout.py` | Simulates rollout controller decisions, exercises TACL energy validator and release gate CLI, persists audit trail artifacts. | Establishes negative scenarios (`degraded_packet_loss`) and ensures automatic rollback audit entries are emitted.【F:tests/e2e/test_progressive_rollout.py†L1-L130】
| Core orchestration guardrails | `tests/core/orchestrator/test_mode_orchestrator.py` | Property-style tests over guard bands, dwell timers, and state transitions for the mode orchestrator. | Ensures state machine reacts to metric breaches and timeouts across all macro states.【F:tests/core/orchestrator/test_mode_orchestrator.py†L1-L170】
| Agent prompt safety | `tests/core/agent/test_prompt_manager.py` | Prompt rendering, truncation, experimentation rollback, and record-id determinism. | Covers agent prompt hygiene; does **not** exercise scheduler logic, leaving CronExpression paths untested.【F:tests/core/agent/test_prompt_manager.py†L1-L160】
| Data backfill planner | `tests/data/test_backfill_planner.py` | Validates gap detection and inferred frequency for historical data rebuilds. | Ensures cache-aware backfill cadence stays deterministic for trading venues.【F:tests/data/test_backfill_planner.py†L1-L17】
| Compliance and risk chaos | `tests/core/test_compliance_chaos.py` | Executes regulatory validator under chaos-span instrumentation. | Confirms compliance violations surface telemetry suitable for chaos audits.【F:tests/core/test_compliance_chaos.py†L1-L33】
| Contract baselines | `tests/contracts/test_openapi_contracts.py` | Diff-freeze of OpenAPI schema, route coverage, headers, and version metadata. | Acts as source of truth for API shape, RBAC headers, and compatibility guarantees.【F:tests/contracts/test_openapi_contracts.py†L1-L53】
| Thermodynamic assertions | `tests/tacl/test_validate_energy.py` | Validates free-energy decomposition, degradation detection, and CLI artifact creation. | Ties YAML scenarios to artifact generation for CI consumption.【F:tests/tacl/test_validate_energy.py†L1-L55】
| Evolution CLI smoke | `tests/evolution/test_bond_evolver_cli.py` | Ensures CLI emits topology JSON for bond evolver. | CLI-level coverage only; genetic optimizer internals lack direct unit tests.【F:tests/evolution/test_bond_evolver_cli.py†L1-L34】

### 1.2 Thermodynamic control loops

| Asset | Location | Purpose |
| --- | --- | --- |
| TACL validator CLI | `tacl/validate.py` | Loads scenario fixtures, runs EnergyValidator, and writes JSON/Markdown artifacts for CI.【F:tacl/validate.py†L1-L142】
| Release gate evaluator | `tacl/release_gates.py` | Enforces latency, coverage, performance budgets, nominal free energy, and negative scenarios with artifact emission.【F:tacl/release_gates.py†L1-L150】
| Scenario fixtures | `tacl/link_activator_test_scenarios.yaml` | Defines `nominal`, `degraded_high_latency`, and `degraded_packet_loss` telemetry baselines consumed by both CLIs.【F:tacl/link_activator_test_scenarios.yaml†L1-L25】

### 1.3 Infrastructure (Go / Terratest)

| Suite | Location | Focus |
| --- | --- | --- |
| EKS validation | `infra/terraform/tests/eks_validation_test.go` | Wraps `terraform init -validate` with connectivity diagnostics, deadline awareness, and skips when registry outages occur.【F:infra/terraform/tests/eks_validation_test.go†L1-L165】
| Registry connectivity classifier | `infra/terraform/tests/eks_validation_connectivity_test.go` | Unit-tests error unwrapping helpers detecting Terraform registry outages vs configuration errors.【F:infra/terraform/tests/eks_validation_connectivity_test.go†L1-L73】

### 1.4 UI and telemetry (Playwright)

| Suite | Location | Focus |
| --- | --- | --- |
| Dashboard signals e2e | `ui/dashboard/tests/e2e/dashboard.spec.ts` | Validates render latency budget, accessibility (axe-core), and semantic guardrail hook for CLIP embeddings.【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L158】
| Accessibility smoke | `ui/dashboard/tests/accessibility.test.js` | (Not inspected in-depth here) – should align with L7 guard once tags are applied. |

### 1.5 Baseline release metrics

* Latency, coverage, and negative-scenario gates are codified in `ci/release_gates.yml` with current coverage at 93.7%, latency p95 ≤ 85 ms, and explicit negative scenarios.【F:ci/release_gates.yml†L1-L14】
* Latest thermodynamic artifact (`.ci_artifacts/energy_validation.md`) records nominal free energy ≈ 1.26 and entropy ≈ 0.41 in smoke mode, forming the baseline for regressions.【F:.ci_artifacts/energy_validation.md†L1-L8】

## 2. Component coverage matrix

| Component | Critical functionality | Existing coverage | Coverage gaps |
| --- | --- | --- | --- |
| Analytical core (`core/*`) | Mode orchestration, guard bands, recovery pathways | `tests/core/orchestrator/test_mode_orchestrator.py` exercises multi-state transitions under stochastic guard breaches.【F:tests/core/orchestrator/test_mode_orchestrator.py†L1-L170】 | Strategy scheduler (`core/agent/scheduler.py`) lacks direct tests despite complex Cron parsing and SLA enforcement logic; current agent tests focus on prompt management rather than scheduling.【F:core/agent/scheduler.py†L1-L160】【F:tests/core/agent/test_prompt_manager.py†L1-L160】
| Data ingest & backfill | Frequency inference, gap detection | `tests/data/test_backfill_planner.py` validates cadence inference for gap fills.【F:tests/data/test_backfill_planner.py†L1-L17】 | Need chaos/backpressure coverage for resampling, planner error handling, and integration with live resync loops.
| Risk & compliance | Regulatory validator chaos instrumentation | `tests/core/test_compliance_chaos.py` asserts black swan metadata triggers violations and traces chaos spans.【F:tests/core/test_compliance_chaos.py†L1-L33】 | No regression suite covering risk budget drift within the trading loop; guard to be tied into L5 chaos scenarios.
| TACL stability loop (`tacl/*`) | Energy validation CLI, release gates, scenario fixtures | `tests/tacl/test_validate_energy.py` plus CI CLIs ensure free-energy monotonicity and artifact generation.【F:tests/tacl/test_validate_energy.py†L1-L55】【F:tacl/validate.py†L1-L142】【F:tacl/release_gates.py†L1-L150】 | Need stochastic perturbation suites for entropy spikes and scenario drift beyond YAML fixtures.
| Trading lifecycle (E2E) | CLI backtest, TradePulseSystem, OMS integration | `tests/e2e/test_full_pipeline.py` and `tests/e2e/test_trading_cycle.py` cover offline and live paths respectively.【F:tests/e2e/test_full_pipeline.py†L1-L132】【F:tests/e2e/test_trading_cycle.py†L1-L116】 | Missing chaos/L5 coverage for degraded connectors and latency injection within OMS.
| Evolutionary optimizer | Genetic topology search & CLI | CLI smoke ensures JSON artifact, but no unit-level assertions on crossover/mutation strategies.【F:tests/evolution/test_bond_evolver_cli.py†L1-L34】 | Add deterministic seed-based tests for `evolution/bond_evolver.py` operators and constraint handling.
| API contracts | OpenAPI schema, RBAC headers | Contract suites validate schema equality, path coverage, and headers.【F:tests/contracts/test_openapi_contracts.py†L1-L53】 | Need to ensure every new public endpoint updates schemas and contract tests in tandem.
| Infrastructure | Terraform/EKS validation | Terratest suite validates init/validate and classifies connectivity outages.【F:infra/terraform/tests/eks_validation_test.go†L1-L165】 | Expand to cover policy-as-code assertions (network policies, IAM) and apply to production tfvars.
| UI & telemetry | Signals dashboard render, accessibility, semantic guardrails | Playwright suite enforces latency, accessibility, and optional CLIP baseline.【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L158】 | Need Playwright tags for L7 and synthetic packet-loss/perf diff ingestion to align with perf budgets.

## 3. Level taxonomy & enforcement plan

| Level | Scope | Required enforcement |
| --- | --- | --- |
| **L0** | Static analysis, lint, typing, secret scanning (`tests.yml` lint job, security workflow) | Consolidate lint + secret checks under Stage A/B with caching via `actions/setup-python` and `actions/cache` already present.【F:.github/workflows/tests.yml†L29-L98】【F:.github/workflows/security.yml†L1-L63】
| **L1** | Pure unit tests (no network/filesystem beyond tmp) | Apply `@pytest.mark.l1` with pytest marker definitions in `pytest.ini`; forbid external I/O via fixtures.
| **L2** | Contracts, schema, RBAC, audit trail | Tag OpenAPI and pact suites with `l2`; enforce mutation detection when schema diff occurs.【F:tests/contracts/test_openapi_contracts.py†L1-L53】
| **L3** | Integration suites (core modules, backfill, feature computation) | Tag relevant `tests/data/**`, `tests/core/**` integration scenarios; ensure deterministic seeds.
| **L4** | End-to-end regressions (`tests/e2e/**`) | Tag pipeline and trading cycle tests `l4`; run in Stage D with artifact uploads.
| **L5** | Stability & degradation (chaos, TACL gates, rollout) | Tag chaos suites and TACL CLI-driven e2e; ensure `tacl.validate --run ci` and `tacl.release_gates` run every PR.【F:tacl/validate.py†L54-L122】【F:tests/e2e/test_progressive_rollout.py†L1-L130】
| **L6** | Infrastructure readiness (Terratest) | Enforce Go prefix `TestL6_` (to be introduced) and ensure Terratest job stays in Stage F.【F:infra/terraform/tests/eks_validation_test.go†L1-L165】
| **L7** | UI/UX, accessibility, render performance | Adopt Playwright tags and ensure traces uploaded per Stage F.【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L158】
| **UNSTABLE** | Flaky quarantine | New pytest marker `unstable` declared in `pytest.ini` for triage, automatically escalates PR risk.

Automated enforcement is implemented via `tests/_helpers/quality_levels.py`, which maps every historical suite to an explicit `l?` marker during collection.【F:tests/_helpers/quality_levels.py†L1-L130】 The root `conftest.py` injects the resolved marker and records it in `item.user_properties`, guaranteeing no anonymous tests enter the pipeline.【F:conftest.py†L320-L341】 Regression tests assert that future paths remain classified and surface actionable errors whenever contributors add untracked suites.【F:tests/unit/tools/test_quality_level_registry.py†L1-L35】

## 4. GitHub Actions consolidation roadmap

Stage alignment for the existing workflows:

1. **Stage A – Repository hygiene & security**: combine `.github/workflows/tests.yml` lint job preamble and `.github/workflows/security.yml` secret/dependency scans; both already set up Python 3.11 with caching.【F:.github/workflows/tests.yml†L29-L98】【F:.github/workflows/security.yml†L1-L63】
2. **Stage B – Static analysis**: extend lint job to emit structured summaries; include Terraform fmt/validate and SBOM when merging with `sbom.yml` (not detailed here).
3. **Stage C – L1/L2 pytest suites**: configure `pytest -m "l1 or l2"` execution and ensure contract artifacts upload; coverage gating aligned with release gate config.【F:ci/release_gates.yml†L1-L14】
4. **Stage D – L3/L4 integrations**: run full integration and E2E suites, collecting artifacts from pipeline and trading cycle regressions.【F:tests/e2e/test_full_pipeline.py†L1-L132】【F:tests/e2e/test_trading_cycle.py†L1-L116】
5. **Stage E – L5 stability gates**: reuse `thermodynamic-validation.yml` (`python -m tacl.validate --run ci`) and `progressive-release-gates.yml` to assert free energy, latency, coverage, and negative scenarios.【F:.github/workflows/thermodynamic-validation.yml†L1-L41】【F:.github/workflows/progressive-release-gates.yml†L1-L33】【F:tacl/release_gates.py†L53-L133】
6. **Stage F – L6/L7 readiness**: Terratest Go suites and Playwright jobs ensure environment and dashboard budgets remain within bounds.【F:infra/terraform/tests/eks_validation_test.go†L1-L165】【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L158】
7. **Stage G – Reporting**: Aggregate `.ci_artifacts/energy_validation.*`, `.ci_artifacts/release_gates.*`, coverage reports, Terraform logs, and Playwright traces for PR consumption as mandated.【F:tacl/validate.py†L42-L51】【F:tacl/release_gates.py†L29-L36】【F:.ci_artifacts/energy_validation.md†L1-L8】 The aggregator `tools/ci/pr_summary.py` consumes those artifacts together with stage results to emit a machine-readable JSON and Markdown summary per PR, including risk level computation derived from release gates and thermodynamic outcomes.【F:tools/ci/pr_summary.py†L1-L156】 Repository hygiene is verified ahead of Stage A through `tools/ci/verify_repository_layout.py`, ensuring TradePulse core, TACL, Terraform, and dashboard surfaces exist before downstream tests run.【F:tools/ci/verify_repository_layout.py†L1-L103】

Caching for Python/Node/Go dependencies is already configured via `actions/cache` invocations in the test workflow and should be extended to UI (Playwright) jobs to maintain throughput.【F:.github/workflows/tests.yml†L29-L151】

## 5. Gap remediation backlog

1. **Agent scheduler determinism** – introduce `l1` and `l3` tests for cron parsing, SLA violation paths, and jitter handling in `core/agent/scheduler.py`; seed randomness to comply with anti-flake policy.【F:core/agent/scheduler.py†L1-L194】
2. **Evolutionary optimizer internals** – add deterministic seeds and unit tests for crossover/mutation, ensuring reproducible graph structures beyond CLI smoke.【F:tests/evolution/test_bond_evolver_cli.py†L1-L34】
3. **OMS degradation scenarios** – craft `l5` tests injecting latency/packet loss into OMS connectors, verifying release gates trigger rollback (extend `tests/e2e/test_progressive_rollout.py`).【F:tests/e2e/test_progressive_rollout.py†L1-L130】
4. **UI performance regressions** – integrate Playwright performance budgets with `configs/perf_budgets.yaml` via Stage F and persist traces per PR.【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L158】【F:tacl/release_gates.py†L53-L133】
5. **Risk drift monitoring** – expand chaos suite to include VaR drift detection within trading cycle, aligning with compliance invariants.【F:tests/core/test_compliance_chaos.py†L1-L33】

## 6. Stability & flake management

* All stochastic suites must pin seeds (see orchestrator tests for precedent) and adopt `@pytest.mark.unstable` for quarantined cases until remediated.【F:tests/core/orchestrator/test_mode_orchestrator.py†L81-L147】
* L1/L2 suites must avoid real network access; rely on fixtures/mocks consistent with secure sandbox expectations.
* Terraform connectivity classifiers already distinguish outage vs misconfiguration; reuse this pattern for other external integrations.【F:infra/terraform/tests/eks_validation_connectivity_test.go†L1-L73】

## 7. Reporting & governance

* Ensure Stage G artifacts publish machine-readable JSON (energy, release gates, perf diffs) and human-readable Markdown, following the helper implementations in `tacl.validate` and `tacl.release_gates`.【F:tacl/validate.py†L42-L121】【F:tacl/release_gates.py†L29-L133】
* Risk posture for each PR should include: coverage delta, energy metrics (free energy, entropy), latency p95/p99/max vs budgets, contract status, infrastructure validation result, UI accessibility/perf result, and performance regression diff.
* Enforce merge blocks whenever `ci/release_gates.yml` thresholds fail or new public contracts lack updated tests, aligning with the negative scenario coverage presently codified.【F:ci/release_gates.yml†L1-L14】【F:tacl/release_gates.py†L53-L133】

This blueprint should be version-controlled and referenced by contributor documentation so that every PR inherits the reinforced testing expectations.
