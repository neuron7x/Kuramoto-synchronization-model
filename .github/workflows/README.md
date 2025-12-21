# GitHub Actions Workflows - Release Gate System

This directory contains the CI/CD workflows that implement the TradePulse release gate system, inspired by dopamine-based reinforcement learning mechanisms (TD(0) RPE, DDM, Go/No-Go).

## Recent Optimizations (2025-11-16)

To improve development experience and reduce CI time for solo developer workflow, comprehensive optimizations were made:

### Phase 1: Previous Optimizations (2025-11-15)
1. ✅ **Removed `coverage.yml`** - Coverage is already checked in both `ci.yml` and `tests.yml`
2. ✅ **Simplified `pr-release-gate.yml`** - No longer re-runs tests that are already run in other workflows
3. ✅ **Removed duplicate localization checks** in flaky-tests job
4. ✅ **Optimized mutation testing** - Mutation testing on PRs only runs in `ci.yml`, not in separate workflow
5. ✅ **SBOM generation** - Only runs on push to main and releases, not on every PR
6. ✅ **Performance regression tests** - Only runs when performance-critical files change
7. ✅ **NAK CI** - Only runs when nak_controller files change

### Phase 2: Workflow Optimization (2025-11-16 AM)
**Disabled Redundant Workflows on PRs:**
1. ✅ **`pr-quality-summary.yml`** - Redundant with test comments in `tests.yml`
2. ✅ **`pr-quality-labels.yml`** - Label management consolidated in `pr-release-gate.yml`
3. ✅ **`pr-complexity-analysis.yml`** - Complexity analysis covered by `pr-release-gate.yml` risk assessment
4. ✅ **`ci.yml` PR trigger** - Coverage and mutation testing now only in `tests.yml` for PRs (still runs on main)

**Disabled Heavy/Expensive Workflows on PRs:**
5. ✅ **`mlops-orchestration.yml`** - MLOps only needed for production deployments, not PRs
6. ✅ **`sbom.yml`** - SBOM generation only needed for releases
7. ✅ **`load-test.yml`** - Load testing expensive, only needed before releases
8. ✅ **`security.yml`** - Comprehensive security covered by `security-policy-enforcement.yml`
9. ✅ **`semgrep.yml`** - Static analysis covered by `security-policy-enforcement.yml`

**Disabled Specialized Workflows on PRs:**
10. ✅ **`thermodynamic-validation.yml`** - Only needed on main branch merges
11. ✅ **`thermo-evolution.yml`** - Only needed on main branch merges
12. ✅ **`progressive-release-gates.yml`** - Progressive rollout validation only for releases

**Enhanced Path Filtering:**
13. ✅ **`e2e-integration.yml`** - Only runs when e2e/integration code or core modules change

### Phase 3: Resilience & Error Handling (2025-11-16 PM)
**Problem:** Tests consistently failing on PRs due to strict artifact requirements and cascading failures.

**Solutions Implemented:**
1. ✅ **Artifact handling improved** - Changed `if-no-files-found: error` to `warn` for all artifacts
2. ✅ **Always upload artifacts** - Added `if: always()` to all artifact upload steps
3. ✅ **Better test execution** - Added `continue-on-error` with exit code capture
4. ✅ **Graceful coverage handling** - Coverage summary handles missing files without failing
5. ✅ **Resilient localization** - Localization sync failures don't stop workflow
6. ✅ **Go test resilience** - Go/Terraform test failures don't block artifact collection
7. ✅ **Benchmark safety** - Performance benchmarks use `continue-on-error`
8. ✅ **Label update protection** - Try-catch around GitHub API calls

**Result:** Tests now capture all possible debugging information even on failure, providing better developer experience.

See `PR_TEST_FIXES_SUMMARY.md` for detailed technical documentation.

### Phase 4: Enhanced Test Orchestration & Quality Gates (2025-11-17)
**Problem:** Gaps in test coverage visibility, no quality metrics for tests themselves, missing contract validation, and no performance tracking.

**Solutions Implemented:**
1. ✅ **Test Quality Validation** - New tool analyzes test code quality, detects test smells, tracks documentation
2. ✅ **Test Performance Tracking** - Tracks test execution times, identifies slow tests, detects regressions
3. ✅ **Contract/Schema Validation** - New dedicated workflow for L2 (contract) tests
4. ✅ **Test Data Management** - Validates fixtures, cassettes, identifies orphaned test data
5. ✅ **Test Orchestration** - Coordinates execution across all test categories (L0-L7)
6. ✅ **Expanded Critical Coverage** - Increased from 3 to 15 critical modules with strict coverage requirements
7. ✅ **Enhanced Reporting** - JSON reports for all test tools enable better visibility and automation

**New Tools:**
- `tools/testing/orchestrator.py` - Test execution orchestration
- `tools/testing/quality_validator.py` - Test quality analysis with smell detection
- `tools/testing/performance_tracker.py` - Performance tracking and regression detection
- `tools/testing/data_validator.py` - Test data validation and management

**Result:** Comprehensive test quality gates with full visibility into test execution, quality, and performance.

See `PR_TEST_OPTIMIZATION_IMPLEMENTATION.md` for complete documentation.

### Phase 5: Stop-the-Line Enforcement (2025-12-21)
1. ✅ Introduced `stop-the-line-gate` in `tests.yml` to hard-require lint, security, backend, and web checks.
2. ✅ Reinstated coverage guardrail on the PR fast path (95% line / 90% branch) to block regressions instead of only reporting.

**Result:** Deterministic stop-the-line gate that blocks merges when any canonical check or coverage budget is missed.

### Benefits
- **⚡ 60-70% faster PR feedback** - Reduced from ~28 to ~10 active workflows on typical PR
- **💰 Massive CI cost reduction** - Eliminated redundant and expensive workflow executions
- **🎯 Single source of truth** - `tests.yml` is the primary PR quality gate
- **🔧 Easier maintenance** - Less duplication, clearer workflow purposes
- **✅ Maintained quality** - All essential checks (tests, security, dependencies) still present
- **🚀 Solo developer optimized** - Fast iteration without enterprise overhead

## Workflow Overview

### Core Quality Gates

#### 1. `tests.yml` - PRIMARY PR Quality Gate ⭐
**Triggers:** PR to any branch, push to main/develop
**Purpose:** Single source of truth for PR quality - linting + fast tests on PRs; full-suite with strict coverage runs on main/schedule

**Jobs:**
- `lint`: Code style, type checking, security scanning (ruff, black, mypy, detect-secrets)
- `web-lint`: Frontend linting and testing (Prettier, ESLint, TypeScript, Jest)
- `tests`: Unit/integration/e2e subset for fast PR feedback (coverage reported only)
  - Go service tests
  - Terraform validation
  - Python tests with coverage reporting
  - Property-based tests with Hypothesis
  - Localization validation
- `full-test-suite`: Runs on main/schedule/workflow_dispatch with 98% line coverage + 90% branch coverage gate

**Requirements:**
- ✅ PRs: coverage reported (no gate on fast path)
- ✅ Main/schedule: full-test-suite enforces 98% line / 90% branch coverage
- ✅ All linters pass (ruff, black, mypy)
- ✅ No secrets detected
- ✅ All tests passing

**PR Comments:**
- Posts test summary with coverage metrics
- Shows pass/fail status and risk assessment
- Links to detailed reports

#### 2. `ci.yml` - Main Branch CI Pipeline
**Triggers:** Push to main only (PRs disabled - see tests.yml)
**Purpose:** Post-merge CI with sharded coverage and mutation testing

**Jobs:**
- `test-coverage` (sharded 1-3): Runs tests with coverage tracking
- `coverage-aggregate`: Combines coverage and enforces 98% threshold
- `mutation-testing-gate`: Runs mutation testing and enforces 90% kill rate
- `publish-containers`: Builds and publishes Docker images

**Requirements:**
- ✅ Code coverage ≥ 98%
- ✅ Mutation kill rate ≥ 90%
- ✅ All tests passing

**Note:** This workflow provides deeper validation after PRs are merged to main.

#### 3. `mutation-testing.yml` - Full Mutation Suite (Main/Develop only)
**Triggers:** Push to main/develop, workflow_dispatch
**Purpose:** Comprehensive mutation testing validation (not run on PRs)

**Features:**
- Runs full mutmut suite on core, backtest, execution modules
- Posts detailed mutation results
- Enforces 90% kill rate threshold
- Uploads mutation reports as artifacts

### PR Management

#### 4. `pr-release-gate.yml` - Risk Assessment
**Triggers:** PR opened/synchronized to main/develop
**Purpose:** Risk scoring and label management based on PR characteristics

**Features:**
- Calculates risk score based on:
  - Critical files modified (up to 20 points)
  - PR size >500 lines (10 points)
- Applies risk labels: `risk: low`, `risk: medium`, `risk: high`
- Manages quality labels: `quality-gate-failed`, `needs-mutation-testing`, `missing-coverage`, `test-needed`
- Posts risk assessment report
- Does NOT block merge (quality gates enforced by tests.yml)

**Note:** Consolidates functionality from deprecated `pr-quality-labels.yml` and `pr-complexity-analysis.yml`

#### 5. `merge-guard.yml` - Merge Protection
**Triggers:** PR opened/synchronized/labeled to main
**Purpose:** Final gate before merge is allowed

**Features:**
- Validates all required checks passed
- Blocks merge if `quality-gate-failed` label present
- Posts merge status to PR
- Provides actionable next steps

#### 6. `version-gate.yml` - Semantic Versioning
**Triggers:** PR opened/synchronized to main/develop
**Purpose:** Ensures version changes follow semantic versioning

**Features:**
- Validates VERSION file changes
- Checks semantic versioning compliance
- Prevents version conflicts

### Security Workflows

#### 7. `security-policy-enforcement.yml` - PR Security Gate
**Triggers:** PR to main/develop
**Purpose:** Comprehensive security scanning for PRs

**Features:**
- Dependency vulnerability scanning
- Secret detection
- SARIF report generation
- Security policy enforcement

**Note:** Consolidates security checks from deprecated `security.yml` and `semgrep.yml` for PRs

#### 8. `contract-schema-validation.yml` - Contract & Schema Tests (NEW)
**Triggers:** PR to any branch (schema/contract/API changes)
**Purpose:** Validates API contracts and schemas (L2 tests)

**Features:**
- Runs L2 contract and protocol tests
- Validates API schemas and OpenAPI specs
- Enforces 85% contract coverage requirement
- Validates data integrity and API compatibility
- Posts summary comment on PR with results

**Path Filters:**
- schemas/**, contracts/**, api/**, interfaces/**
- tests/contracts/**, tests/protocol/**

**Requirements:**
- ✅ All contract tests passing
- ✅ Contract coverage ≥ 85%
- ✅ Schema validation passing

#### 9. `dependency-review.yml` - Dependency Security
**Triggers:** PR with dependency changes (requirements*.txt)
**Purpose:** Reviews dependency changes for vulnerabilities

**Features:**
- Checks new dependencies against GitHub Advisory Database
- Validates license compliance
- Blocks PRs with high-severity vulnerabilities

### Specialized Workflows (Path-Filtered)

These workflows only run when relevant files change:

#### 9. `nak-ci.yml` - NaK Controller Tests
**Triggers:** Changes to `nak_controller/**`
**Purpose:** Validates NaK (Na⁺/K⁺-ATPase) controller implementation

#### 10. `neural-controller-ci.yml` - Neural Controller Tests
**Triggers:** Changes to `tradepulse/neural_controller/**`
**Purpose:** Tests neural network controller components

#### 11. `dopamine-validation.yml` - Dopamine System Tests
**Triggers:** Changes to dopamine config/code
**Purpose:** Validates dopamine-based reward system

#### 12. `helm.yml` - Helm Chart Validation
**Triggers:** Changes to `deploy/helm/**`
**Purpose:** Lints and validates Kubernetes Helm charts

#### 13. `e2e-integration.yml` - E2E Integration Tests
**Triggers:** Changes to e2e tests or core modules
**Purpose:** Runs end-to-end integration test suite

#### 14. `performance-regression-pr.yml` - Performance Tests
**Triggers:** Changes to performance-critical code
**Purpose:** Detects performance regressions in core execution paths

#### 15. `multi-exchange-replay-regression.yml` - Replay Tests
**Triggers:** Changes to recordings, backtest, or execution code
**Purpose:** Validates market replay functionality across exchanges

### Disabled Workflows (No Longer Run on PRs)

The following workflows have been disabled on PRs to reduce CI overhead:

#### ❌ `pr-quality-summary.yml` (Disabled)
**Reason:** Redundant with test comments posted by `tests.yml`
**How to Re-enable:** Change trigger from `workflow_dispatch` to `workflow_run`

#### ❌ `pr-quality-labels.yml` (Disabled)
**Reason:** Label management consolidated in `pr-release-gate.yml`
**How to Re-enable:** Change trigger from `workflow_dispatch` to `pull_request_target`

#### ❌ `pr-complexity-analysis.yml` (Disabled)
**Reason:** Complexity analysis covered by `pr-release-gate.yml` risk assessment
**How to Re-enable:** Change trigger from `workflow_dispatch` to `pull_request`

#### ❌ `ci.yml` PR Trigger (Disabled)
**Reason:** Coverage and mutation testing now handled by `tests.yml` for PRs
**Note:** Still runs on push to main for post-merge validation
**How to Re-enable:** Add `pull_request` trigger back to workflow

#### ❌ `mlops-orchestration.yml` PR Trigger (Disabled)
**Reason:** MLOps deployment validation only needed for production, not development PRs
**How to Re-enable:** Uncomment `pull_request` section in workflow file

#### ❌ `sbom.yml` PR Trigger (Disabled)
**Reason:** SBOM generation expensive and only needed for releases
**How to Re-enable:** Uncomment `pull_request` section in workflow file

#### ❌ `load-test.yml` PR Trigger (Disabled)
**Reason:** Load testing is expensive and only needed before major releases
**How to Re-enable:** Uncomment `pull_request` section in workflow file

#### ❌ `security.yml` PR Trigger (Disabled)
**Reason:** Security scanning consolidated in `security-policy-enforcement.yml`
**Note:** Still runs weekly on schedule and on push to main/develop
**How to Re-enable:** Uncomment `pull_request` section in workflow file

#### ❌ `semgrep.yml` PR Trigger (Disabled)
**Reason:** Static analysis covered by `security-policy-enforcement.yml`
**Note:** Still runs weekly on schedule and on push to main/develop
**How to Re-enable:** Uncomment `pull_request` section in workflow file

#### ❌ `thermodynamic-validation.yml` PR Trigger (Disabled)
**Reason:** Thermodynamic validation only needed on main branch merges
**How to Re-enable:** Uncomment `pull_request` section in workflow file

#### ❌ `thermo-evolution.yml` PR Trigger (Disabled)
**Reason:** Thermodynamic evolution tests only needed on main branch
**How to Re-enable:** Uncomment `pull_request` section in workflow file

#### ❌ `progressive-release-gates.yml` PR Trigger (Disabled)
**Reason:** Progressive rollout validation only for actual releases
**How to Re-enable:** Uncomment `pull_request` section in workflow file

### Main Branch Only Workflows

These workflows only run on push to main/develop (not on PRs):

#### `enterprise-cicd.yml`
Full enterprise deployment pipeline with:
- Quality gates
- Unit and integration tests
- Container building and signing
- Infrastructure planning
- Canary deployments
- Progressive rollouts
- Automated rollback

#### `deploy-environments.yml`
Environment-specific deployments

#### `sbom-generation.yml`
Comprehensive SBOM generation with signing

#### `slsa-provenance.yml`
SLSA provenance generation for supply chain security

## Quality Requirements

### PR Quality Gates (Enforced by tests.yml)

#### Coverage Requirements
- **Line Coverage:** ≥ 98% for critical modules (`core/`, `backtest/`, `execution/`)
- **Branch Coverage:** ≥ 90% across the codebase
- **Test Files:** PRs must include or update tests for new functionality

**Local check:**
```bash
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98
```

#### Linting and Type Checking
- **ruff:** Python code style and quality checks
- **black:** Python code formatting
- **mypy:** Python static type checking with strict mode
- **slotscheck:** Validates `__slots__` definitions

**Local check:**
```bash
ruff check .
black --check .
mypy
```

#### Security Scanning
- **detect-secrets:** No hardcoded secrets in code
- **shellcheck:** Shell script validation
- **Localization:** All translation keys properly defined

#### Go and Terraform
- **Go tests:** Service-level unit tests must pass
- **Terraform validation:** Infrastructure code must be valid

### Main Branch Quality Gates (Enforced by ci.yml)

#### Mutation Testing (90%)
Test suite must kill at least 90% of mutants to ensure test quality.
Only enforced on main branch to reduce PR overhead.

**Local check:**
```bash
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9
```

#### Sharded Coverage
Deep coverage analysis with 3-way sharding for comprehensive validation.

## Risk Levels

### 🟢 Low Risk (0-24 points)
- Standard review process
- Automated checks sufficient
- Can be merged by any team member with approval

### 🟡 Medium Risk (25-49 points)
- Requires careful review
- Multiple approvals recommended
- Should have comprehensive testing

### 🔴 High Risk (50+ points)
- **Requires senior review**
- Extensive testing mandatory
- Phased rollout recommended
- Consider feature flags

## PR Labels

### Quality Labels
- `quality-gate-failed` (🔴): Quality requirements not met - **merge blocked**
- `missing-coverage` (🟠): Coverage below threshold
- `test-needed` (🔴): Tests must be added or updated
- `needs-mutation-testing` (🟠): Mutation testing required

### Risk Labels
- `risk: low` (🟢): Low risk, standard process
- `risk: medium` (🟡): Medium risk, careful review needed
- `risk: high` (🔴): High risk, senior review required

## Artifacts

All workflows generate artifacts for review:

### Coverage Reports
- `coverage.xml`: Cobertura format
- `coverage_html/`: Browsable HTML report

### Mutation Reports
- `mutation_summary.json`: Metrics in JSON
- `.mutmut-cache`: Full mutation cache
- `html/`: Browsable mutation report

### Quality Reports
- `quality-gate-reports`: Combined quality metrics

## Branch Protection

To enforce these gates, configure branch protection on `main`:

### Required Status Checks (Essential for PRs)
- ✅ `Tests (Python 3.11)` - Primary quality gate from tests.yml
- ✅ `Lint & Type Check (Python 3.11)` - Code quality from tests.yml
- ✅ `Merge Guard Quality Check` - Final merge validation
- ✅ `Quality Assessment & Risk Labeling` - Risk assessment from pr-release-gate.yml

### Optional Status Checks (Component-Specific)
These only run when relevant files are changed:
- `Helm Charts` - Only if Helm charts modified
- `E2E Integration Tests` - Only if e2e/core code modified
- `Performance Regression Detection` - Only if performance-critical code modified
- `NAK CI` - Only if nak_controller modified
- `Neural Controller CI` - Only if neural_controller modified
- `Dopamine Config Validation` - Only if dopamine config modified

### Additional Settings
- ✅ Require pull request reviews (1 reviewer minimum)
- ✅ Require conversation resolution
- ✅ Dismiss stale reviews on new commits
- ❌ Do not allow bypassing settings
- ❌ Do not allow force pushes

## Troubleshooting

### Coverage Below 98%
1. Check the test summary comment on your PR for details
2. Run locally: `pytest --cov-report=term-missing`
3. Identify uncovered lines
4. Add tests for uncovered code paths
5. Push changes to re-trigger checks

### Tests Failing
1. Review the "Test & Coverage Summary" comment on your PR
2. Check workflow logs for detailed error messages
3. Run failing tests locally: `pytest tests/path/to/test.py -v`
4. Fix issues and push changes

### Linting Errors
1. Run linters locally before pushing:
   ```bash
   ruff check .
   black --check .
   mypy
   ```
2. Auto-fix formatting: `black .`
3. Fix other issues reported by ruff and mypy

### Security Issues Detected
1. Check `security-policy-enforcement.yml` workflow for details
2. Run secret scan locally: `detect-secrets scan`
3. Remove any hardcoded secrets or credentials
4. Use environment variables or secrets management

### Quality Gate Blocking Merge
1. Check PR comments for specific failures from tests.yml
2. Review workflow logs in the Actions tab
3. Fix identified issues
4. Push changes - checks re-run automatically

### High Risk Label Applied
1. Review risk factors in pr-release-gate.yml comment
2. Consider breaking into smaller PRs if >500 lines changed
3. Ensure comprehensive test coverage for critical files
4. Risk is informational only - doesn't block if quality gates pass

### Need to Re-Enable a Disabled Workflow
If you need a workflow that was disabled:
1. Find the workflow file in `.github/workflows/`
2. Follow the "How to Re-enable" instructions in the workflow comments
3. Or refer to the "Disabled Workflows" section above
4. Note: Consider if the workflow is truly needed for PR validation

### Workflow Not Running
Some workflows only run when specific files change:
- Check the `paths:` section in the workflow file
- Ensure your PR touches files in those paths
- Path-filtered workflows: helm, e2e-integration, performance-regression-pr, nak-ci, neural-controller-ci, dopamine-validation

## Local Development

### Quick Pre-Push Checklist

Before pushing, run these essential checks locally to catch issues early:

```bash
# 1. Run linters (fast, catches most issues)
ruff check .
black --check .
mypy

# 2. Run tests with coverage
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98

# 3. Check for secrets (important!)
detect-secrets scan

# Optional: Run mutation testing (slow, only needed for critical changes)
# mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
# python -m tools.mutation.kill_rate_guard --threshold=0.9

# Push if all pass
git push origin your-branch
```

### Fast Iteration Tips

For faster development cycle:

```bash
# Auto-fix formatting issues
black .

# Run only specific tests
pytest tests/path/to/test.py -v

# Run tests in parallel (faster)
pytest -n auto

# Skip slow tests during development
pytest -m "not slow"
```

### What Runs on Your PR

When you push to a PR, only these workflows will run (much faster than before):

**Always Run:**
- `tests.yml` - Linting, type checking, unit/integration tests (5-10 min)
- `pr-release-gate.yml` - Risk assessment and labeling (1-2 min)
- `merge-guard.yml` - Final merge check (< 1 min)
- `security-policy-enforcement.yml` - Security scanning (2-3 min)

**Conditionally Run (only if relevant files changed):**
- `helm.yml` - If Helm charts changed
- `e2e-integration.yml` - If e2e or core modules changed
- `performance-regression-pr.yml` - If performance-critical code changed
- `nak-ci.yml` - If nak_controller changed
- `neural-controller-ci.yml` - If neural_controller changed
- `dopamine-validation.yml` - If dopamine config changed

**Total PR wait time:** 5-15 minutes (vs 30-60 minutes before optimization)

## Summary of Active PR Workflows

After optimization, these workflows run on PRs:

| Workflow | Always Runs | Path-Filtered | Purpose |
|----------|-------------|---------------|---------|
| tests.yml | ✅ | ❌ | Primary quality gate: tests, linting, coverage |
| pr-release-gate.yml | ✅ | ❌ | Risk assessment and labeling |
| merge-guard.yml | ✅ | ❌ | Final merge validation |
| security-policy-enforcement.yml | ✅ | ❌ | Security scanning |
| version-gate.yml | ✅ | ❌ | Semantic versioning validation |
| dependency-review.yml | ❌ | ✅ | Dependency security (requirements files) |
| dependency-pinning.yml | ❌ | ✅ | Dependency management |
| helm.yml | ❌ | ✅ | Helm chart validation (deploy/helm) |
| e2e-integration.yml | ❌ | ✅ | E2E tests (tests/e2e, core modules) |
| performance-regression-pr.yml | ❌ | ✅ | Performance tests (core/engine, execution) |
| multi-exchange-replay-regression.yml | ❌ | ✅ | Replay tests (recordings, backtest) |
| nak-ci.yml | ❌ | ✅ | NaK controller (nak_controller/) |
| neural-controller-ci.yml | ❌ | ✅ | Neural controller (neural_controller/) |
| dopamine-validation.yml | ❌ | ✅ | Dopamine config validation |
| ci-hardening.yml | ❌ | ✅ | Workflow security (.github/workflows) |

**Total:** ~15 workflows (down from 28+) with smart path filtering

## References

- [CI/CD Overview](../../docs/CI_CD_OVERVIEW.md) - Complete CI/CD documentation with local commands
- [Release Process](../../docs/RELEASE_PROCESS.md) - How to create and manage releases
- [Release Gates Documentation](../../docs/RELEASE_GATES.md) - Quality gate thresholds and enforcement
- [Quality Gates](../../docs/quality_gates.md) - Automated governance and pre-commit stack
- [Operations Guide](../../docs/OPERATIONS.md)
- [Testing Guide](../../TESTING.md)

---

**Last Updated:** 2025-12-02
**Version:** 2.1.0 - Added comprehensive CI/CD and release documentation
