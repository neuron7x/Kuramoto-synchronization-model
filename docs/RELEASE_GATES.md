# Release Gates - Minimal Core Engine Pipeline

## Overview

This document describes the TradePulse release gate system. **As of December 2025**, we have consolidated from R&D chaos to a single, reliable "release-gate" pipeline focusing on the core engine: `backtest/`, `execution/`, and `core runtime` under `src/tradepulse/`.

**Philosophy:** Small but always green beats huge but flaky.

## Current Enforced Gates (CI-Required)

### Primary Release Gate Workflow

**File:** `.github/workflows/release-gate.yml`

**What it does:**
- ✅ Linting (ruff, black)
- ✅ Type checking (mypy on core modules)
- ✅ Unit tests for core engine (backtest, execution, runtime)
- ✅ Fast (< 10-15 minutes)
- ✅ Stable (always green, no flaky tests)

**Scope:**
- Tests: `tests/unit/backtest/`, `tests/unit/execution/`, `tests/execution/`, `tests/core/`, `tests/integration/test_backtest.py`
- Code: `core/`, `backtest/`, `execution/`, `src/tradepulse/`
- Excludes: slow tests, heavy_math tests, nightly tests, flaky tests

**Local reproduction:**
```bash
# Install dependencies
pip install --upgrade pip setuptools wheel
pip install -c constraints/security.txt -r requirements.txt
pip install -c constraints/security.txt -r requirements-dev.txt

# Run lint
ruff check .
black --check .
mypy core/ backtest/ execution/ src/tradepulse/

# Run core tests
pytest \
  tests/unit/backtest/ \
  tests/unit/execution/ \
  tests/execution/ \
  tests/integration/test_backtest.py \
  tests/core/ \
  --ignore=tests/core/agent/ \
  --ignore=tests/core/orchestrator/ \
  -m "not slow and not heavy_math and not nightly and not flaky" \
  --maxfail=5 \
  --tb=short \
  --quiet
```

## Advanced Quality Requirements (Legacy/Aspirational)

These requirements existed in previous iterations but are NOT currently enforced in the release-gate due to flakiness and complexity. They represent future goals.

### 1. Code Coverage Gate (98% minimum)
All pull requests must maintain **98% code coverage** across critical modules:
- `core/`, `backtest/`, `execution/`
- Configured in `pyproject.toml`: `fail_under = 98`
- Enforced in: `.github/workflows/ci.yml`, `.github/workflows/coverage.yml`

**Local check:**
```bash
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98
```

### 2. Mutation Testing Gate (90% kill rate minimum)
All PRs must achieve **90% mutation kill rate**:
- Ensures test quality, not just coverage
- Configured in `pyproject.toml`: `[tool.mutmut]`
- Enforced by: `tools/mutation/kill_rate_guard.py`

**Local check:**
```bash
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9
```

### 3. Risk-Based Review Requirements
PRs are automatically assigned risk levels (low/medium/high) based on:
- Coverage gap (up to 40 points)
- Mutation gap (up to 40 points)
- Critical files modified (up to 20 points)
- PR size (10 points for >500 lines)

High-risk changes require senior review and extensive testing.

## Progressive Release Gates

The Progressive Rollout pipeline promotes builds through additional quality gates:

1. **Latency Gate** – uses `observability.release_gates.ReleaseGateEvaluator`
   with the following thresholds (milliseconds):
   - median ≤ 60
   - p95 ≤ 85
   - max ≤ 120
2. **Coverage Gate (Legacy)** – superseded by 98% requirement above
3. **Performance Budget Gate** – asserts that each component listed in
   `configs/perf_budgets.yaml` stays within its budget.  Budgets are expressed in
   milliseconds measured by the synthetic benchmark harness.
4. **Energy Regression Gate** – reuses the TACL validator to ensure the selected
   scenario stays under the free energy limit (1.35).  Negative scenarios must
   fail validation; otherwise the job fails loudly to prevent silent regressions.

## Metrics Sources

- Latency samples originate from the link activator replay harness and are
  recorded in `ci/release_gates.yml`.
- Coverage data comes from the merged coverage report published by the test
  pipeline.
- Performance metrics come from the offline benchmark runner that writes the
  latest observations into `configs/perf_budgets.yaml`.
- Energy metrics reuse the same fixtures as the thermodynamic validation step
  (`tacl/link_activator_test_scenarios.yaml`).

## Experimental/Non-Blocking Workflows

The following workflows are EXPERIMENTAL and do NOT block merges:

### Mutation Testing (`.github/workflows/mutation-testing.yml`)
- **Status:** Manual workflow_dispatch only
- **Purpose:** Assess test quality (90% kill rate goal)
- **Why disabled:** Very slow (60-90 min), can be run periodically

### Performance Regression (`.github/workflows/performance-regression.yml`)
- **Status:** Main branch only, manual dispatch
- **Purpose:** Detect performance degradations
- **Why disabled:** Flaky, slow, not critical for correctness

### Load Testing (`.github/workflows/load-test.yml`)
- **Status:** Manual workflow_dispatch only
- **Purpose:** Heavy load testing (HTTP + gRPC)
- **Why disabled:** Very expensive, only needed before major releases

### MLOps Orchestration (`.github/workflows/mlops-orchestration.yml`)
- **Status:** Main branch + schedule only
- **Purpose:** Production deployment orchestration
- **Why disabled:** Not relevant for PR validation

All experimental workflows are clearly marked with:
```yaml
# EXPERIMENTAL: <description>
# This workflow does not block merges - see .github/workflows/release-gate.yml for core gates
```

## Other Active Workflows

### Critical (Still Run on PRs)
1. **tests.yml** - Legacy comprehensive test suite (still active, but being superseded by release-gate.yml)
2. **security-policy-enforcement.yml** - Security scanning
3. **pr-release-gate.yml** - Risk assessment (informational, non-blocking)
4. **dependency-review.yml** - Dependency security

### Component-Specific (Path-Filtered)
These only run when specific files change:
- `helm.yml` - Helm chart validation
- `nak-ci.yml` - NaK controller tests
- `dopamine-validation.yml` - Dopamine config validation
- `e2e-integration.yml` - E2E tests

### Main Branch Only
- `ci.yml` - Post-merge coverage and deep validation
- `enterprise-cicd.yml` - Full deployment pipeline
- `sbom-generation.yml` - SBOM generation

## PR Labels

The system automatically applies labels:
- `quality-gate-failed` (red): Merge blocked
- `risk: low/medium/high` (green/yellow/red): Risk level
- `missing-coverage`, `test-needed`: Specific issues

## Branch Protection

Configure branch protection on `main` to require:
- ✅ **Release Gate - Lint & Type Check**
- ✅ **Release Gate - Core Tests (backtest, execution, runtime)**
- ⚠️ **tests.yml** - Legacy test suite (optional, can be removed once release-gate is proven)

Optional (informational):
- `pr-release-gate.yml` - Risk assessment (does not block)
- `security-policy-enforcement.yml` - Security scanning

## Failure Semantics

When any gate fails:

### Quality Gates (Coverage/Mutation)
- Workflow posts detailed comment to PR
- Applies `quality-gate-failed` label
- Blocks merge automatically
- Uploads artifacts: `coverage.xml`, `mutation_summary.json`

### Progressive Release Gates
- Workflow emits structured artifacts in `.ci_artifacts/release_gates.json` and `.ci_artifacts/release_gates.md`
- Contains: failing gate name, raw metrics, energy/entropy data
- Exits with code **1**, pipeline halts

### Resolution
- Fix identified issues locally
- Push changes to re-trigger checks
- All required checks must pass before merge
- Consult `docs/OPERATIONS.md` for remediation guidance

## Flaky Tests Backlog

Tests marked as `flaky` are excluded from the release gate and tracked here for future fixing:

| Test | Reason | Issue |
|------|--------|-------|
| (To be populated as flaky tests are identified) | | |

Use `@pytest.mark.flaky` to mark tests that need fixing but shouldn't block CI.

---
**Updated:** 2025-12-09 - Consolidated to minimal core engine release gate (Phase 1 complete)
