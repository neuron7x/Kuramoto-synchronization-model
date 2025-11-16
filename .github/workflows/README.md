# GitHub Actions Workflows - Release Gate System

This directory contains the CI/CD workflows that implement the TradePulse release gate system, inspired by dopamine-based reinforcement learning mechanisms (TD(0) RPE, DDM, Go/No-Go).

## Recent Optimizations (2025-11-15)

To improve development experience and reduce CI time, the following optimizations were made:

### Removed Redundancies
1. ✅ **Removed `coverage.yml`** - Coverage is already checked in both `ci.yml` and `tests.yml`
2. ✅ **Simplified `pr-release-gate.yml`** - No longer re-runs tests that are already run in other workflows
3. ✅ **Removed duplicate localization checks** in flaky-tests job
4. ✅ **Optimized mutation testing** - Mutation testing on PRs only runs in `ci.yml`, not in separate workflow
5. ✅ **SBOM generation** - Only runs on push to main and releases, not on every PR
6. ✅ **Performance regression tests** - Only runs when performance-critical files change
7. ✅ **NAK CI** - Only runs when nak_controller files change

### Benefits
- **Faster PR feedback** - Fewer redundant jobs
- **Reduced CI minutes** - No duplicate test execution
- **Clearer separation of concerns** - Each workflow has a specific purpose
- **Better resource usage** - Heavy jobs only run when needed

## Workflow Overview

### Core Quality Gates

#### 1. `ci.yml` - Main CI Pipeline
**Triggers:** PR to any branch, push to main
**Purpose:** Comprehensive testing with coverage and mutation testing gates

**Jobs:**
- `test-coverage` (sharded 1-3): Runs tests with coverage tracking
- `coverage-aggregate`: Combines coverage and enforces 98% threshold
- `mutation-testing-gate`: Runs mutation testing and enforces 90% kill rate
- `publish-containers`: Builds and publishes Docker images (main/develop only)

**Requirements:**
- ✅ Code coverage ≥ 98%
- ✅ Mutation kill rate ≥ 90%
- ✅ All tests passing

#### 2. `mutation-testing.yml` - Mutation Testing (Push to main/develop only)
**Triggers:** Push to main/develop, workflow_dispatch
**Purpose:** Validates test quality through mutation testing

**Note:** Mutation testing is also included in `ci.yml` for PRs. This workflow runs the full mutation suite on pushes to main branches.

**Features:**
- Runs mutmut on core, backtest, execution modules
- Posts detailed mutation results to PR
- Enforces 90% kill rate threshold
- Uploads mutation reports as artifacts

### PR Management

#### 3. `pr-release-gate.yml` - Risk Assessment (No duplication)
**Triggers:** PR opened/synchronized
**Purpose:** Risk scoring based on PR characteristics

**Optimizations:**
- ✅ **No longer re-runs tests** - relies on tests.yml and ci.yml workflows
- ✅ **No duplicate coverage checks** - coverage is validated in tests.yml
- ✅ **No duplicate mutation testing** - mutation testing runs in ci.yml

**Features:**
- Calculates risk score based on:
  - Critical files modified (up to 20 points)
  - PR size >500 lines (10 points)
- Applies risk labels: `risk: low`, `risk: medium`, `risk: high`
- Posts risk assessment report
- Does NOT block merge (quality gates are in other workflows)

#### 5. `pr-quality-labels.yml` - Auto-Labeling
**Triggers:** PR opened/synchronized
**Purpose:** Automatically applies quality-related labels

**Labels Applied:**
- `test-needed`: No test files modified
- `missing-coverage`: Coverage below threshold
- `risk: low/medium/high`: Risk assessment
- `quality-gate-failed`: Quality requirements not met
- `needs-mutation-testing`: Mutation testing required

#### 6. `merge-guard.yml` - Merge Protection
**Triggers:** PR opened/synchronized/labeled
**Purpose:** Final check before merge is allowed

**Features:**
- Validates all required checks passed
- Blocks merge if `quality-gate-failed` label present
- Posts merge status to PR
- Provides actionable next steps

#### 7. `pr-quality-summary.yml` - Aggregated Reports
**Triggers:** After CI workflows complete
**Purpose:** Posts comprehensive quality summary

**Features:**
- Downloads artifacts from completed workflows
- Aggregates coverage and mutation metrics
- Posts summary table to PR
- Links to detailed workflow runs

### Other Workflows

#### `enterprise-cicd.yml`
Full enterprise deployment pipeline with:
- Quality gates
- Unit and integration tests
- Container building and signing
- Infrastructure planning
- Canary deployments
- Progressive rollouts
- Automated rollback

## Quality Requirements

### Coverage (98%)
All critical modules (`core/`, `backtest/`, `execution/`) must maintain 98% line coverage.

**Local check:**
```bash
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98
```

### Mutation Testing (90%)
Test suite must kill at least 90% of mutants to ensure test quality.

**Local check:**
```bash
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9
```

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

### Required Status Checks
- ✅ `Aggregate coverage & enforce guardrail`
- ✅ `Mutation Testing Gate (90% kill rate)`
- ✅ `Merge Guard Quality Check`

### Additional Settings
- ✅ Require pull request reviews (1 for standard, 2 for high-risk)
- ✅ Require conversation resolution
- ❌ Do not allow bypassing settings

## Troubleshooting

### Coverage Below 98%
1. Run locally: `pytest --cov-report=term-missing`
2. Identify uncovered lines
3. Add tests for uncovered code paths
4. Push changes to re-trigger checks

### Mutation Kill Rate Below 90%
1. Run locally: `mutmut run`
2. Review survivors: `mutmut show`
3. Improve tests to detect mutations
4. Re-run to verify
5. Push changes

### Quality Gate Blocking Merge
1. Check PR comments for specific failures
2. Review workflow logs
3. Fix identified issues
4. Push changes - checks re-run automatically

### High Risk Label Applied
1. Review risk factors in PR comment
2. Consider breaking into smaller PRs
3. Ensure comprehensive test coverage
4. Request senior review
5. Risk is informational only - doesn't block if quality gates pass

## Local Development

Before pushing:

```bash
# Run tests with coverage
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98

# Run mutation testing (slower, optional)
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9

# Run linters
ruff check .
black --check .
mypy

# Push if all pass
git push origin your-branch
```

## References

- [Release Gates Documentation](../../docs/RELEASE_GATES.md)
- [Operations Guide](../../docs/OPERATIONS.md)
- [Testing Guide](../../TESTING.md)

---

**Last Updated:** 2025-11-11
**Version:** 1.0.0
