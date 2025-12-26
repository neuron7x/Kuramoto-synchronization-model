---
owner: docs@tradepulse
review_cadence: monthly
last_reviewed: 2025-12-25
status: active
links:
  - ../DOCUMENTATION_SUMMARY.md
  - ./documentation_quality_metrics.md
---

# Metrics Contract: Claims vs Evidence

> **Purpose**: Single source of truth for TradePulse quality/performance/security claims.
>
> All coverage, performance, security, and compliance claims in README.md, TESTING.md, SECURITY.md,
> and docs/** must reference this document for their evidence status.
>
> **Last Updated**: 2025-12-25
> **Maintainer**: TradePulse Team

## ⚠️ Important Disclaimers

1. **This is NOT a legal document.** It does not constitute a warranty, guarantee, or contractual commitment.
2. **This document requires regular maintenance.** Claims and statuses must be updated after documentation changes, releases, and evidence collection.
3. **Do not rely on this document if it has not been updated in the last 30 days.**
4. **Claims with status other than `proven` require independent verification before production decisions.**

---

## Status Definitions

| Status | Meaning | CI Verified? |
|--------|---------|--------------|
| `proven` | Real report/log exists AND live script/test reproduces it | ✅ Yes |
| `partial` | Partial evidence (old log, not in CI, or incomplete coverage) | ⚠️ Partial |
| `goal` | Target/roadmap item, no technical proof yet | ❌ No |
| `remove` | Claim too bold/unprovable, should be removed from docs | ❌ N/A |

**Legacy statuses** (mapped to above):
- `enforced` → `proven` (CI gate active)
- `design_target` → `goal`
- `design_aligned` → `partial` (code present, no external audit)
- `internal_claim` → `partial`
- `planned` → `goal`

---

## CI Workflow Notes

> **Note on workflow status reporting**: Some workflows may show as "failure" with 0 jobs
> on documentation-only PRs or feature branches. This is expected GitHub Actions behavior:
>
> - **tests.yml**: Skips runs for `.md` and `docs/**` changes (paths-ignore filter)
> - **sbom.yml**: Only runs on push to `main`/`develop` branches
> - **ci.yml**: Only runs on push to `main`
> - **deploy-environments.yml**: Only runs on `staging`/`production` branches
> - **ci-hardening.yml**: Only runs when `.github/workflows/**` files change
>
> When code changes are present, these workflows execute correctly.

---

## Claims Registry

### Coverage Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| COV_98_CI_GATE | coverage | 98% CI coverage gate enforced on all PRs | `pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98` | `.github/workflows/tests.yml`, `reports/coverage/` | goal | Target gate, currently not met. See actual coverage below. |
| COV_BACKTEST_74 | coverage | backtest/ module ~74% coverage | `pytest tests/unit/backtest tests/integration/test_backtest.py tests/integration/test_golden_path_backtest.py --cov=backtest --cov-report=term` | `reports/coverage/index.html` | proven | Measured 2025-12-10: 73.85%. Key files: engine.py (95%), performance.py (96%), dopamine_td.py (92%) |
| COV_EXECUTION_44 | coverage | execution/ module ~44% coverage | `pytest tests/unit/execution tests/integration/ --cov=execution --cov-report=term -m "not slow"` | `reports/coverage/index.html` | proven | Measured 2025-12-10: 43.61%. Key files: paper_trading.py (98%), connectors.py (68%), order_lifecycle.py (74%) |
| COV_CORE_32 | coverage | core modules ~32% coverage | `pytest tests/unit/core tests/integration/ --cov=core --cov-report=term -m "not slow"` | `reports/coverage/index.html` | proven | Measured 2025-12-10: 32.05%. High coverage: engine/core.py (95%), orchestrator (96%), maintenance/backups (95%) |
| COV_BACKTEST_100 | coverage | backtest/ module 100% coverage | `pytest --cov=backtest tests/` | `reports/coverage/index.html` | goal | Long-term target, not enforced in CI |
| COV_EXECUTION_100 | coverage | execution/ module 100% coverage | `pytest --cov=execution tests/` | `reports/coverage/index.html` | goal | Long-term target, not enforced in CI |
| COV_CORE_90_95 | coverage | core modules 90-95% coverage | `pytest --cov=core tests/` | `reports/coverage/index.html` | goal | Long-term target, not enforced in CI |
| COV_AGENT_95 | coverage | core/agent/ ≥95% coverage | `pytest --cov=core/agent tests/` | `reports/coverage/index.html` | goal | Per TESTING.md |
| COV_DATA_95 | coverage | core/data/ ≥95% coverage | `pytest --cov=core/data tests/` | `reports/coverage/index.html` | goal | Per TESTING.md |
| COV_INDICATORS_90 | coverage | core/indicators/ ≥90% coverage | `pytest --cov=core/indicators tests/` | `reports/coverage/index.html` | goal | Per TESTING.md |
| COV_METRICS_95 | coverage | core/metrics/ ≥95% coverage | `pytest --cov=core/metrics tests/` | `reports/coverage/index.html` | goal | Per TESTING.md |
| COV_PHASE_95 | coverage | core/phase/ ≥95% coverage | `pytest --cov=core/phase tests/` | `reports/coverage/index.html` | goal | Per TESTING.md |
| COV_GOLDEN_PATH | coverage | Golden path backtest workflow covered | `make golden-path` | `tests/integration/test_golden_path_backtest.py`, `Makefile:232-258` | proven | Verified 2025-12-12: Complete workflow (data→analysis→backtest) runs in <30s with deterministic output. 21 integration tests. |
| COV_PAPER_TRADING | coverage | Paper trading engine >95% coverage | `pytest tests/unit/execution/test_paper_trading.py --cov=execution.paper_trading` | `tests/unit/execution/test_paper_trading.py` | proven | 44 unit tests, 98% coverage of paper_trading.py |
| MUTATION_90_KILL | coverage | 90% mutation kill rate | `mutmut run --use-coverage && python -m tools.mutation.kill_rate_guard --threshold 0.9` | `reports/mutmut/summary.json` | partial | Configured in pyproject.toml, CI workflow exists but experimental |

### Performance Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| PERF_1M_BARS_SEC | performance | 1M+ bars/second backtesting throughput | `pytest tests/performance/ --benchmark-enable` | `reports/perf/` | goal | Architecture target, no verified benchmark |
| PERF_SUB5MS_ORDER | performance | Sub-5ms order latency (exchange dependent) | Live trading benchmark | N/A | goal | Depends on exchange latency, needs live testing |
| PERF_SUB1MS_SIGNAL | performance | Sub-1ms signal generation with cached indicators | `pytest tests/performance/test_indicator_benchmarks.py --benchmark-enable` | `reports/perf/` | partial | Benchmark exists but not enforced in CI |
| PERF_200MB_MEMORY | performance | ~200MB steady-state memory for live trading | Memory profiling | N/A | goal | Not automated |
| PERF_GPU_ACCEL | performance | GPU acceleration (5-50x speedup) | `python -c "import cupy"` + benchmark | N/A | goal | CuPy integration exists, CUDA kernels not fully implemented |
| PERF_FLOAT32_50PCT | performance | Float32 reduces memory by 50% | `pytest tests/performance/` | docs/performance.md | partial | Documented, basic tests exist |
| PERF_FRONTEND_LCP | performance | LCP ≤ 2.0s desktop, ≤ 2.5s mobile | `npx lighthouse-ci` | N/A | goal | Per docs/performance.md |
| PERF_FRONTEND_TTFB | performance | TTFB ≤ 500ms | `npx lighthouse-ci` | N/A | goal | Per docs/performance.md |
| PERF_LATENCY_P95_85MS | performance | p95 latency ≤ 85ms for release gate | `python scripts/validate_energy.py --metric latency_p95=<value>` | `.ci_artifacts/release_gates.json` | partial | CI gate exists in progressive rollout |
| PERF_LATENCY_P99_120MS | performance | p99 latency ≤ 120ms for release gate | `python scripts/validate_energy.py --metric latency_p99=<value>` | `.ci_artifacts/release_gates.json` | partial | CI gate exists in progressive rollout |

### CI/CD Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| CI_FAST_GATES_15MIN | ci | Fast PR gates complete in ≤15 minutes | GitHub Actions workflow run | `.github/workflows/tests.yml:55-532` | proven | Verified 2025-12-12: lint (8min timeout), fast-unit-tests (15min timeout), security-fast (10min timeout) |
| CI_HEAVY_JOBS_GATED | ci | Heavy jobs only run on main/schedule/manual | N/A | `.github/workflows/tests.yml:541,665,758` | proven | full-test-suite, mutation-testing, benchmarks have if-conditions preventing PR runs |
| CI_CACHE_STRATEGY | ci | Unique venv cache keys per job type | N/A | `.github/workflows/tests.yml:84-89,212-217,499-502` | proven | Cache keys: venv-lint, venv-full, venv-bench, venv-mutation, venv-security |
| CI_LOCAL_MATCH | ci | Local make targets match CI commands | `make test` | `Makefile:89-93`, `.github/workflows/tests.yml:309-322` | proven | Verified 2025-12-12: `make test` uses same pytest markers as CI fast gates |
| TEST_FAST_PASSED | testing | Fast test suite passes (PR gate) | `make test` | Local test run 2025-12-12 | proven | 3512 passed, 18 skipped in ~3 minutes. All core tests green. |

### Reliability Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| REL_PRODUCTION_GRADE | reliability | Production-grade algorithmic trading platform | N/A | README.md | goal | Live trading in beta status |
| REL_ENTERPRISE_GRADE | reliability | Enterprise-grade security and reliability | N/A | README.md | partial | Patterns implemented, not battle-tested at scale |
| REL_TRL7 | reliability | TRL7 (internal post-staging assessment) | N/A | docs/TACL.md | partial | Internal assessment only, no external validation |
| REL_API_AVAIL_995 | reliability | Client API availability ≥99.5% SLA | Prometheus/Grafana | docs/reliability.md | goal | SLA target documented, production metrics TBD |
| REL_API_AVAIL_999 | reliability | Client API availability 99.9% SLO | Prometheus/Grafana | docs/reliability.md | goal | Internal SLO target |
| REL_STRATEGY_997 | reliability | Strategy runtime 99.7% success rate | Prometheus/Grafana | docs/reliability.md | goal | SLO target documented |
| REL_ORDER_EXEC_999 | reliability | Order execution 99.9% within broker SLA | Prometheus/Grafana | docs/reliability.md | goal | SLO target documented |
| REL_MARKET_DATA_998 | reliability | Market data freshness 99.8% < 1.5s | Prometheus/Grafana | docs/reliability.md | goal | SLO target documented |
| REL_BACKTEST_CRASH_001 | reliability | Backtest exception handling validated | `pytest tests/reliability/test_backtest_crash_handling.py -v` | tests/reliability/test_backtest_crash_handling.py, .github/workflows/reliability-smoke.yml | proven | 6 tests validate graceful failure on exceptions |
| REL_DATA_MISSING_001 | reliability | NaN/missing data detection validated | `pytest tests/reliability/test_missing_market_data.py -v` | tests/reliability/test_missing_market_data.py, .github/workflows/reliability-smoke.yml | proven | 9 tests validate data quality checks before backtest |
| REL_EXEC_TIMEOUT_001 | reliability | Execution timeout handling validated | `pytest tests/reliability/test_execution_adapter_failures.py -v` | tests/reliability/test_execution_adapter_failures.py, .github/workflows/reliability-smoke.yml | proven | 7 tests validate timeout/connection error handling |
| REL_CONFIG_INVALID_001 | reliability | Invalid configuration handling validated | `pytest tests/reliability/test_invalid_config.py -v` | tests/reliability/test_invalid_config.py, .github/workflows/reliability-smoke.yml | proven | 12 tests validate configuration error detection |
| REL_PROCESS_INT_001 | reliability | Process interruption handling validated | `pytest tests/reliability/test_process_interruption.py -v` | tests/reliability/test_process_interruption.py, .github/workflows/reliability-smoke.yml | partial | 6 tests validate cleanup logic (simplified signal handling) |
| REL_SCENARIOS_DOC | reliability | Failure scenarios documented | N/A | docs/RELIABILITY_SCENARIOS.md | proven | 13 canonical failure scenarios documented with reproduction steps |

### Security & Compliance Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| SEC_NO_EXTERNAL_AUDIT | security | No external security audit performed | N/A | SECURITY.md | proven | Explicitly stated disclaimer |
| SEC_NIST_800_53 | compliance | Controls aligned with NIST SP 800-53 | N/A | docs/security/, SECURITY.md | partial | Design patterns present, NO external audit |
| SEC_ISO_27001 | compliance | Controls aligned with ISO 27001 | N/A | docs/security/, SECURITY.md | partial | Framework followed, NO certification |
| SEC_SEC_FINRA | compliance | Patterns for SEC/FINRA compliance | N/A | SECURITY.md | partial | Controls present, NO regulatory audit |
| SEC_GDPR_CCPA | compliance | Privacy controls for GDPR/CCPA | N/A | docs/security/ | partial | Privacy patterns implemented, NO formal audit |
| SEC_SOC2 | compliance | SOC 2-aligned telemetry and controls | N/A | SECURITY.md | partial | Telemetry present, NO SOC 2 examination |
| SEC_EU_AI_ACT | compliance | EU AI Act alignment (human oversight) | N/A | SECURITY.md, docs/TACL.md | partial | Manual reset endpoints documented |
| SEC_PIP_AUDIT | security | Python dependencies vulnerability-free | `make audit` | `pip-audit` output | partial | CI enforced; lockfiles pin narwhals to 2.9.0. Latest `audit/artifacts/pip_audit.json` reports 0 vulnerabilities; regenerate with the locked 2.9.0 during the next monthly audit cycle to eliminate version drift. |
| SEC_BANDIT_SCAN | security | Static security analysis passes | `bandit -r core/ backtest/ execution/ src/ -ll -q` | CI output | proven | CI enforced |
| SEC_SECRETS_SCAN | security | No secrets in codebase | `detect-secrets scan` | CI output | proven | CI enforced in tests.yml |
| SEC_CONTAINER_SCAN | security | Container images scanned for vulnerabilities | Trivy/Grype in CI | Security workflow | partial | Workflow exists, critical vulns block |
| SEC_TLS_13 | security | TLS 1.3 enforced for all connections | `sslyze` scan | docs/security/ | partial | Documented requirement, weekly scan |
| SEC_AES_256 | security | AES-256 encryption at rest | N/A | SECURITY.md | partial | Configuration documented, no audit |
| SEC_VAULT_SECRETS | security | HashiCorp Vault for secrets management | N/A | SECURITY.md | partial | Integration documented |
| SEC_MFA_ADMIN | security | MFA support for admin operations | N/A | SECURITY.md, README.md | partial | Code present, not validated |
| SEC_AUDIT_400_DAY | security | 400-day audit log retention | N/A | SECURITY.md | partial | Configuration documented |
| SEC_7_YEAR_THERMO | security | 7-year TACL audit retention | N/A | SECURITY.md, docs/TACL.md | partial | Design documented, production TBD |

### Responsible AI & Fairness Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| FAIR_BIAS_GUARDS | fairness | Bias metrics (demographic parity, equal opportunity) validated | `pytest tests/test_metric_validations.py -q` | `tests/test_metric_validations.py`, `src/risk/fairness_metrics.py` | proven | Unit tests cover metric correctness and threshold enforcement for auditability. |

### TACL (Thermodynamic Autonomic Control Layer) Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| TACL_FREE_ENERGY_135 | reliability | Free energy ≤ 1.35 for rollout | `python scripts/validate_energy.py` | `.ci_artifacts/energy_validation.json` | partial | CI gate exists in release workflow |
| TACL_MONOTONIC_DESCENT | reliability | Monotonic free energy descent constraint | N/A | runtime/thermo_controller.py | partial | Code implemented, no production validation |
| TACL_CRISIS_RECOVERY | reliability | Adaptive crisis recovery with GA/RL | N/A | runtime/thermo_controller.py | partial | Code implemented |
| TACL_PROTOCOL_HOTSWAP | reliability | Zero-downtime protocol hot-swap | N/A | tacl/ | partial | Code present |
| TACL_CIRCUIT_BREAKER | reliability | Hardware circuit breaker for human override | N/A | SECURITY.md | partial | Documented design |

### Product Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| PROD_50_INDICATORS | product | 50+ geometric/technical indicators | `find core/indicators -name "*.py" ! -name "__init__.py" \| wc -l` | core/indicators/ | partial | Directory exists, exact count needs verification |
| PROD_MULTI_EXCHANGE | product | Multi-exchange support (Binance, Coinbase, Kraken, Alpaca) | N/A | execution/adapters/ | partial | Adapters exist, live testing TBD |
| PROD_KILL_SWITCH | product | Emergency kill switch for trading halt | N/A | runtime/, SECURITY.md | partial | Code present |
| PROD_PAPER_TRADING | product | Paper trading mode | N/A | execution/paper_trading.py | partial | Code exists |
| PROD_WALK_FORWARD | product | Walk-forward optimization | N/A | backtest/ | partial | Documented capability |
| PROD_PROPERTY_TESTS | product | Property-based testing with Hypothesis | `pytest tests/property/` | tests/property/ | proven | Tests exist and run in CI |
| PROD_FUZZ_TESTS | product | Fuzz testing | `pytest tests/fuzz/` | tests/fuzz/ | proven | Tests exist and run in CI |
| PROD_RISK_GUARDIAN | product | Risk Guardian drawdown protection | `tp risk-guardian simulate` | money_proof/ | partial | Scripts present, no production data |

### Other Claims

| id | domain | claim | measurement_command | evidence_path | status | notes |
|----|--------|-------|---------------------|---------------|--------|-------|
| OTHER_CORE_STABLE | other | Core Engine production ready | N/A | README.md | partial | Per component maturity table |
| OTHER_LIVE_BETA | other | Live Trading in beta | N/A | README.md | proven | Explicitly stated as beta |
| OTHER_DASHBOARD_ALPHA | other | Web Dashboard in alpha | N/A | README.md | proven | Explicitly stated as early preview |
| OTHER_DOCS_85PCT | other | Documentation 85% complete | N/A | README.md | partial | Self-reported estimate |

---

## Verification Commands Quick Reference

### Coverage

```bash
# Generate full coverage report
make test-coverage

# View HTML report
open reports/coverage/index.html

# Run with CI gate threshold
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98
```

### Performance

```bash
# Run performance benchmarks
make perf

# Run specific indicator benchmarks
pytest tests/performance/test_indicator_benchmarks.py --benchmark-enable

# Run microbenchmarks
python bench/bench_indicators.py --repeat 10 --warmup 5
```

### Security

```bash
# Run security audits (pip-audit + bandit)
make audit

# Run full security test suite
make security-test

# Scan for secrets
.venv/bin/detect-secrets scan core backtest execution src application
```

### TACL Energy Validation

```bash
# Validate energy metrics
python scripts/validate_energy.py --metric latency_p95=75.0 --metric cpu_burn=0.65

# Show TACL configuration
python scripts/validate_energy.py --show-config
```

### Mutation Testing

```bash
# Run mutation testing
make mutation-test

# Or manually
mutmut run --use-coverage
python -m tools.mutation.kill_rate_guard --threshold 0.9
```

---

## Maintenance Requirements

1. **After each PR**: Update claims if documentation changes
2. **After each release**: Review all `goal` items and update statuses
3. **Monthly**: Verify `partial` claims still have valid evidence
4. **Quarterly**: Review compliance claims with security team
5. **Annually**: Consider external audit for `partial` security/compliance items

---

## Changelog

| Date | Change |
|------|--------|
| 2025-12-19 | Updated roadmap with 2024 achievements and 2025 progress milestones |
| 2025-12-19 | Added Q1 2026 roadmap with v1.0 release targets |
| 2025-12-19 | Updated project-status.md with detailed component maturity matrix |
| 2025-12-19 | Updated production readiness assessment to 75-85% |
| 2025-12-11 | Added 6 reliability claims with proven status: failure scenario tests (40 tests), documentation |
| 2025-12-11 | Created tests/reliability/ with comprehensive failure mode validation |
| 2025-12-11 | Added docs/RELIABILITY_SCENARIOS.md documenting 13 canonical failure scenarios |
| 2025-12-11 | Created .github/workflows/reliability-smoke.yml for fast failure mode testing |
| 2025-12-10 | Added realistic coverage measurements: backtest (73%), execution (44%), core (32%) |
| 2025-12-10 | Added COV_GOLDEN_PATH and COV_PAPER_TRADING claims with proven status |
| 2025-12-10 | Updated COV_98_CI_GATE to goal status (target, not currently enforced at 98%) |
| 2025-12-10 | Added CI Workflow Notes section explaining workflow trigger behavior |
| 2025-12-10 | Expanded to full table format with id, domain, measurement_command, evidence_path, notes |
| 2025-12-10 | Added TACL, product, and other domain claims |
| 2025-12-10 | Consolidated status definitions (proven/partial/goal/remove) |

---

**⚠️ WARNING**: This document does NOT constitute a security audit, compliance certification,
or performance guarantee. All claims with status other than `proven` require independent
verification before relying on them for production decisions.
