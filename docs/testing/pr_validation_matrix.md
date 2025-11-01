# TradePulse PR Validation Hardening

## 1. Repository Test Inventory

### 1.1 Catalogue of automated suites
| Stack | Location | Framework | Primary coverage | TradePulse level |
| --- | --- | --- | --- | --- |
| Core analytics & data | `tests/core/**`, `tests/data/**`, `tests/analysis/**`, `tests/analytics/**`, `tests/unit/**`, `tests/utils/**` | pytest | Indicators, scheduling, idempotency, backfill/resampling, numerical safety nets | L1 |
| Contracts & interfaces | `tests/contracts/**`, `tests/api/**`, `tests/interfaces/**`, `tests/protocol/**`, `tests/sdk/**`, `tests/security/**`, `tests/observability/**` | pytest | REST/OpenAPI schema, RBAC & audit trail, CLI/API contracts, telemetry surfaces | L2 |
| Cross-module integrations | `tests/integration/**`, `tests/execution/**`, `tests/strategies/**`, `tests/evolution/**`, `tests/neuro/**`, `tests/neuropro/**`, `tests/scripts/**`, `tests/workflows/**`, `tests/sandbox/**`, root level `tests/test_*.py` | pytest | Portfolio lifecycle, execution adapters, evolutionary CLI, administrative workflows | L3 |
| End-to-end regressions | `tests/e2e/**`, `tests/smoke/**` | pytest | Synthetic full pipeline runs, live trading cycle simulations, smoke orchestration | L4 |
| Resilience & thermodynamics | `tests/chaos/**`, `tests/performance/**`, `tests/fuzz/**`, `tests/nightly/**`, `tests/tacl/**`, `tests/e2e/test_progressive_rollout.py` | pytest | Chaos injections, performance benchmarks, TACL free-energy gates, rollout decisions | L5 |
| Infrastructure readiness | `infra/terraform/tests/*.go` | Go + Terratest | EKS provisioning, Terraform registry connectivity, policy enforcement | L6 |
| Dashboard UI & telemetry | `ui/dashboard/tests/**/*.js`, `ui/dashboard/tests/e2e/*.spec.ts` | Node runner, Playwright + axe-core | Dashboard rendering, trace headers, accessibility, semantic guardrails | L7 |

### 1.2 Component coverage and gaps
| Component | Critical function | Automated coverage | Gaps / required follow-ups |
| --- | --- | --- | --- |
| Core agent orchestration (`core/agent/*`) | Safety transitions, cooldown heuristics, scheduling SLA enforcement | Mode orchestrator breach handling and guard rails stress-tested via property-style parametrization【F:tests/core/orchestrator/test_mode_orchestrator.py†L1-L155】; scheduler back-pressure and SLA miss logic exercised with deterministic fake clocks【F:tests/unit/test_agent_scheduler.py†L1-L57】 | Add deterministic coverage for agent memory persistence and prompt cache eviction – no direct tests target `core/agent/memory` yet |
| Data backfill & resampling (`core/data/backfill.py` et al.) | Gap detection, layered cache reconciliation, planner retries | Planner behaviour under retries and checksum failures validated with synthetic caches and loaders【F:tests/unit/data/test_backfill_executor.py†L9-L80】; streaming aggregators assert single-gap recovery and refresh semantics【F:tests/unit/data/test_streaming_aggregator.py†L66-L164】 | Introduce chaos-style latency + packet loss injections for resample workers to ensure L5 parity with TACL degradation scenarios |
| Portfolio + execution pipeline | Full ingest → signal → execution cycle | Synthetic CLI-driven pipeline builds artifacts end-to-end, validating reporting exports and idempotent writes【F:tests/e2e/test_full_pipeline.py†L1-L78】; live trading cycle simulation asserts OMS state, connector responses, and PnL accounting【F:tests/e2e/test_trading_cycle.py†L1-L117】 | Extend coverage for cross-venue hedging and partial fill recovery, currently modelled only for single-venue Binance sandbox |
| TACL stability loop (`tacl/*`) | Free energy thresholds, entropy penalties, artifact emission | Validator normalises weights, catches degraded scenarios, and produces audit artifacts for failing runs【F:tests/tacl/test_validate_energy.py†L1-L65】【F:tests/tacl/test_validate_energy.py†L66-L97】 | Add regression ensuring `EnergyValidator` handles concurrent scenario execution and caches negative test traces for audit |
| Evolutionary optimiser (`evolution/bond_evolver.py`) | CLI workflow, serialized topology outputs | CLI smoke test ensures JSON topology emission, structural sanity, and logged artifacts【F:tests/evolution/test_bond_evolver_cli.py†L9-L34】 | Expand stochastic seed determinism checks to guarantee reproducibility and add UNSTABLE quarantine hooks when mutation heuristics change |
| API contracts & audit (`application/api`, `observability/audit`) | OpenAPI schemas, RBAC, trace headers, audit redaction | Baseline schema equality, header enforcement, and idempotency metadata validated against golden files【F:tests/contracts/test_openapi_contracts.py†L1-L75】; system audit trail redacts sensitive fields while keeping actions observable【F:tests/api/test_system_audit_trail.py†L1-L32】 | Add JSON-schema conformance for streaming WebSocket contracts and ensure audit payload hashing is validated under high-volume bursts |
| Infrastructure (Terraform/EKS) | Registry reachability, module validation under deadlines | Connectivity error classification isolates transient registry outages to avoid false positives【F:infra/terraform/tests/eks_validation_connectivity_test.go†L1-L54】; Terraform validate job enforces deadlines and handles registry failures gracefully【F:infra/terraform/tests/eks_validation_test.go†L92-L140】 | Add packet-loss simulation against private module sources and RBAC assertion for IAM policies |
| Dashboard UX & telemetry (`ui/dashboard`) | Render latency, accessibility compliance, trace propagation | Playwright spec enforces latency budgets, WCAG AA rules, and semantic guardrails for signal rendering【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L111】; node smoke tests validate exports, trace headers, and component rendering while labelling as L7 gates【F:ui/dashboard/tests/test.js†L1-L46】【F:ui/dashboard/tests/accessibility.test.js†L1-L49】 | Introduce Playwright trace comparison to baseline artefacts and instrument slow-motion capture for progressive rendering |

### 1.3 Baseline metrics
* Release gates enforce coverage ≥92% with current observed baseline at 93.7%, and latency budgets of p95 ≤85 ms / max ≤120 ms; negative scenarios must fail the gates to expose regressions【F:ci/release_gates.yml†L1-L14】【F:.ci_artifacts/release_gates.md†L1-L8】.
* Thermodynamic validation captures nominal free energy ≈1.2636 and entropy ≈0.4102 as the reference envelope for TACL【F:.ci_artifacts/energy_validation.md†L1-L8】.

### 1.4 Component ↔ test matrix
| Component | Critical behaviour | Covering suites (by level) |
| --- | --- | --- |
| Strategy orchestration & scheduler | Guard bands, SLA back-pressure | `tests/core/orchestrator/test_mode_orchestrator.py` (L1)【F:tests/core/orchestrator/test_mode_orchestrator.py†L1-L148】, `tests/unit/test_agent_scheduler.py` (L1)【F:tests/unit/test_agent_scheduler.py†L1-L57】, `tests/e2e/test_trading_cycle.py` (L4)【F:tests/e2e/test_trading_cycle.py†L1-L117】 |
| Data ingestion & backfill | Gap planner, retry surfaces | `tests/unit/data/test_backfill_executor.py` (L1)【F:tests/unit/data/test_backfill_executor.py†L9-L98】, `tests/integration/test_backfill_gap_fill.py` (L3)【F:tests/integration/test_backfill_gap_fill.py†L1-L41】, `tests/performance/test_memory_regression.py` (L5)【F:tests/performance/test_memory_regression.py†L1-L104】 |
| Risk & compliance | Audit logging, RBAC enforcement | `tests/api/test_system_audit_trail.py` (L2)【F:tests/api/test_system_audit_trail.py†L1-L32】, `tests/contracts/test_openapi_contracts.py` (L2)【F:tests/contracts/test_openapi_contracts.py†L1-L75】, `tests/security/test_rbac_gateway.py` (L2)【F:tests/security/test_rbac_gateway.py†L1-L160】 |
| Thermodynamic control | Free energy descent, degraded scenarios | `tests/tacl/test_validate_energy.py` (L5)【F:tests/tacl/test_validate_energy.py†L1-L97】, `tests/e2e/test_progressive_rollout.py` (L5)【F:tests/e2e/test_progressive_rollout.py†L1-L130】, `python -m tacl.release_gates` (Stage E)【F:.github/workflows/progressive-release-gates.yml†L1-L49】 |
| Full trading cycle | CLI ingest → execution → PnL | `tests/e2e/test_full_pipeline.py` (L4)【F:tests/e2e/test_full_pipeline.py†L1-L78】, `tests/e2e/test_trading_cycle.py` (L4)【F:tests/e2e/test_trading_cycle.py†L1-L117】 |
| Evolution lifecycle | Genetic optimiser topology | `tests/evolution/test_bond_evolver_cli.py` (L3)【F:tests/evolution/test_bond_evolver_cli.py†L9-L34】, `tests/performance/test_indicator_benchmarks.py` (L5)【F:tests/performance/test_indicator_benchmarks.py†L1-L120】 |
| Infrastructure readiness | Terraform validate, registry fallback | `infra/terraform/tests/eks_validation_test.go` (L6)【F:infra/terraform/tests/eks_validation_test.go†L92-L140】, `infra/terraform/tests/eks_validation_connectivity_test.go` (L6)【F:infra/terraform/tests/eks_validation_connectivity_test.go†L1-L54】 |
| UI & telemetry | Rendering latency, accessibility | `ui/dashboard/tests/e2e/dashboard.spec.ts` (L7)【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L111】, `ui/dashboard/tests/accessibility.test.js` (L7)【F:ui/dashboard/tests/accessibility.test.js†L1-L49】 |

## 2. Classification and labelling framework
* Pytest markers for L0–L7 plus `UNSTABLE` are centrally declared in `pytest.ini`, enabling deterministic filtering and enforcing TradePulse testing doctrine across suites.【F:pytest.ini†L1-L22】
* A repository-owned manifest (`tests/test_levels.yaml`) drives the canonical directory and file mappings for each level; adding a suite without updating this manifest fails collection, preventing silent regressions.【F:tests/test_levels.yaml†L1-L49】
* Collection-time enforcement reads the manifest, aligns it with any explicit markers in code, and records the resolved level in item metadata, preventing unclassified tests from running and providing an audit trail for level usage.【F:tests/conftest.py†L1-L170】
* Playwright suites embed `@L7` titles so UI e2e runs expose their level to `--grep` filters, while Node smoke harnesses log the level for downstream parsers.【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L111】【F:ui/dashboard/tests/test.js†L1-L46】
* Terraform Terratests use `TestL6*` prefixes to satisfy the naming convention for infrastructure readiness gates.【F:infra/terraform/tests/eks_validation_test.go†L92-L140】【F:infra/terraform/tests/eks_validation_connectivity_test.go†L9-L54】

## 3. PR pipeline stages (A–G)
| Stage | Purpose | Primary workflows |
| --- | --- | --- |
| A – Supply-chain guardrails | Checkout, secret scan, SBOM / dependency audit | `security.yml` secret & dependency scanning across Bandit, Safety, pip-audit【F:.github/workflows/security.yml†L1-L136】 |
| B – Static analysis | Lint, type-check, Terraform fmt/policy, shell hygiene | `tests.yml` lint job executes Ruff, Black, mypy, slotscheck, shellcheck, detect-secrets, and Terraform validation via Go setup in same workflow stage.【F:.github/workflows/tests.yml†L29-L132】 |
| C – L1 / L2 regression | Unit + contract suites, RBAC checks | `tests.yml` Python test job (unit + contract markers), `e2e-integration.yml` ensures integration-tag gating aligned with L3 handoff.【F:.github/workflows/tests.yml†L100-L199】【F:.github/workflows/e2e-integration.yml†L1-L27】 |
| D – L3 / L4 integrations | Full trading cycle regressions, CLI orchestrations | `tests.yml` high-level tests, targeted `e2e-integration.yml` replays, plus `ci.yml` coverage shards for trading-critical modules.【F:.github/workflows/ci.yml†L12-L66】 |
| E – L5 resilience gates | TACL validation, release gates, progressive rollout | `thermodynamic-validation.yml`, `progressive-release-gates.yml`, and `tests/e2e/test_progressive_rollout.py` executed to ensure free-energy monotonicity and negative scenario detection.【F:.github/workflows/thermodynamic-validation.yml†L1-L52】【F:.github/workflows/progressive-release-gates.yml†L1-L49】【F:tests/e2e/test_progressive_rollout.py†L1-L130】 |
| F – L6 / L7 readiness | Terraform Terratests and Playwright/axe audits | `tests.yml` Go Terraform job, `ui/dashboard` Playwright suite via `test:ui` pipeline, linking to Stage F gating.【F:.github/workflows/tests.yml†L100-L132】【F:ui/dashboard/tests/e2e/dashboard.spec.ts†L1-L111】 |
| G – Reporting | Artifact collation, coverage & performance summaries | `.ci_artifacts` release/energy reports, performance regression outputs uploaded via dedicated workflows for PR review.【F:.ci_artifacts/release_gates.md†L1-L8】【F:.github/workflows/performance-regression.yml†L1-L112】 |

## 4. Gap remediation roadmap
1. **Agent memory & prompt cache** – add deterministic fixtures for `core/agent/memory` and simulate eviction to close L1 gap highlighted in §1.2.
2. **Backfill under degradation** – craft L5 chaos tests with induced packet loss and latency aligned to `degraded_packet_loss` scenario to keep parity with release gates.
3. **Multi-venue execution** – extend L4 e2e tests to include hedging orders and partial fills to ensure risk manager coverage across venues.
4. **WebSocket & audit schemas** – integrate schema validation for streaming endpoints and high-throughput audit hashing to cement L2 guarantees.
5. **Infrastructure packet loss** – expand Terratest coverage for private registries and IAM policies, mirroring Stage E negative scenarios.
6. **UI regression artefacts** – persist Playwright traces and diff them against baselines for deterministic L7 approvals.

## 5. Stability and quarantine policy
* The `UNSTABLE` marker remains available for flaky suites; collection-time labelling appends `tradepulse_level` metadata so elevated-risk PRs can be flagged automatically without suppressing coverage.【F:tests/conftest.py†L99-L127】
* Randomised tests document seeding strategies (e.g., orchestrator property tests) to avoid non-determinism while retaining statistical breadth.【F:tests/core/orchestrator/test_mode_orchestrator.py†L81-L148】

## 6. Baseline expectations post-hardening
* Every PR surfaces coverage deltas, energy metrics, latency budgets, and performance comparisons via `.ci_artifacts` outputs, blocking merges when gates fail.【F:.ci_artifacts/release_gates.md†L1-L8】
* The staged pipeline enumerated in §3 is reproducible, containerised, and devoid of manual toggles, ensuring TradePulse and TACL invariants are continuously enforced for each change.【F:.github/workflows/tests.yml†L29-L199】【F:.github/workflows/progressive-release-gates.yml†L1-L49】
