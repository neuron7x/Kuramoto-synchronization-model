# Tests Workflow Documentation

## Overview

The `tests.yml` workflow has been modernized to 2025 standards with a clear separation between **fast PR gates** and **heavy extended test suites**. This ensures PRs get quick feedback while comprehensive testing runs on a schedule or manually.

## Workflow Structure

### Triggers

```yaml
on:
  pull_request:     # Fast gates run on all PRs
  push:            # Fast gates on all branches, heavy on main only
  schedule:        # Heavy jobs run nightly at 2 AM UTC
  workflow_dispatch: # Manual trigger for heavy jobs
```

### Job Categories

#### 🚀 PR FAST GATES (Required for every PR)

These jobs must complete quickly (≤15 minutes) and run on every pull request:

1. **`detect_ui_changes`** (< 1 min)
   - Detects UI/web changes to conditionally run frontend tests
   - Always runs first

2. **`lint`** (≤ 8 min)
   - **Matrix**: Python 3.11, 3.12
   - Runs: ruff, black, mypy, slotscheck, shellcheck, shfmt
   - Validates: localization bundles, detect-secrets scan
   - **Blocks merge if fails**

3. **`web-lint`** (≤ 5 min)
   - Runs if UI changes detected
   - Executes: Prettier, ESLint, TypeScript type check, Jest unit tests
   - **Blocks merge if fails**

4. **`fast-unit-tests`** (≤ 15 min)
   - **Matrix**: Python 3.11, 3.12
   - **Dependencies**: lint
   - Tests: `pytest -m "not slow and not heavy_math and not nightly and not flaky"`
   - Includes: Go service tests (short mode), smoke tests
   - Coverage: Generates report but does NOT enforce 98% threshold
   - **Blocks merge if fails**

5. **`security-fast`** (≤ 10 min)
   - **Matrix**: Python 3.11
   - **Dependencies**: lint
   - Runs: Bandit (SAST), DAST probes
   - **Blocks merge if fails**

**Total PR gate time: ~10-15 minutes** (parallelized)

#### 🔥 HEAVY / EXTENDED JOBS (Scheduled or manual)

These jobs run ONLY on:
- Push to `main` branch
- Schedule (nightly at 2 AM UTC)
- Manual trigger via workflow_dispatch

1. **`full-test-suite`** (≤ 45 min)
   - **Matrix**: Python 3.11, 3.12
   - **Dependencies**: fast-unit-tests
   - Tests: ALL tests including slow, heavy_math, nightly (excluding flaky)
   - Coverage: **ENFORCES 98% threshold** with `--cov-fail-under=98`
   - Uploads: Full coverage reports (30-day retention)

2. **`mutation-trading-engine`** (≤ 60 min)
   - **Dependencies**: fast-unit-tests
   - Runs: Mutation testing on trading engine core
   - Threshold: 90% mutation kill rate

3. **`benchmarks`** (≤ 30 min)
   - **Dependencies**: fast-unit-tests
   - Runs: Performance regression tests
   - Tracks: Benchmark baselines, performance budgets

4. **`ui_accessibility`** (≤ 15 min)
   - **Condition**: UI changes detected
   - Runs: Playwright accessibility and regression tests on dashboard

5. **`ui-smoke`** (≤ 20 min)
   - **Dependencies**: fast-unit-tests
   - Runs: Playwright smoke tests on web app

6. **`pytest-xdist`** (≤ 30 min)
   - **Dependencies**: fast-unit-tests
   - **Schedule/manual only**
   - Runs: Parallel test profiling with xdist

7. **`flaky-tests`** (≤ 20 min)
   - **Dependencies**: fast-unit-tests
   - **Schedule/manual only**
   - Monitors: Quarantined flaky tests with reruns
   - **Does NOT block** (continue-on-error: true)

## Test Markers

Tests are categorized using pytest markers:

- `slow`: Tests that take > 10 seconds
- `heavy_math`: Compute-intensive tests
- `nightly`: Full regression suites
- `flaky`: Unstable tests (quarantined)
- `smoke`: Quick smoke tests

### Fast PR Tests
```bash
pytest -m "not slow and not heavy_math and not nightly and not flaky"
```

### Full Test Suite
```bash
pytest -m "not flaky"  # All tests except flaky
```

## Caching Strategy

All jobs use optimized caching for speed:

### Python Dependencies
```yaml
cache: 'pip'
cache-dependency-path: |
  requirements.lock
  requirements-dev.lock
  constraints/security.txt
```

### Virtual Environments
Each job type has a unique cache key:
- `venv-lint-{os}-py{version}-{hash}`
- `venv-{os}-py{version}-{hash}` (fast tests)
- `venv-full-{os}-py{version}-{hash}` (full suite)
- `venv-bench-{os}-py3.11-{hash}` (benchmarks)
- etc.

**Cache hit rate optimization**: Dependencies only installed if cache miss.

## Local Reproduction

All CI commands can be reproduced locally:

```bash
# Lint (equivalent to CI lint job)
make lint

# Fast unit tests (equivalent to CI fast-unit-tests)
pytest -m "not slow and not heavy_math and not nightly and not flaky" tests/

# Full test suite (equivalent to CI full-test-suite)
pytest -m "not flaky" tests/ \
  --cov=core --cov=backtest --cov=execution \
  --cov-fail-under=98

# Benchmarks
pytest tests/performance --benchmark-only

# Mutation testing
python -m tools.mutation.trading_engine_suite \
  --reports-dir reports/mutmut/trading_engine --threshold 0.9
```

## Artifact Retention

- **Fast PR artifacts**: 7 days
- **Heavy job artifacts**: 30 days
- **Coverage reports**: Uploaded to Codecov

## Matrix Strategy

Jobs use `fail-fast: false` to see all Python version results even if one fails.

### Python Versions Tested
- **3.11**: Primary version
- **3.12**: Forward compatibility

## Conditional Execution

Heavy jobs use this condition:
```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/main' || 
    github.event_name == 'schedule' || 
    github.event_name == 'workflow_dispatch'
```

## Performance Targets

- **PR fast gates**: ≤ 15 minutes total
- **Full test suite**: ≤ 45 minutes
- **Nightly full run**: ≤ 2 hours

## Observability

### Job Summaries
- Fast tests: Shows line/branch coverage, test counts
- Full suite: Shows coverage vs 98% threshold with risk assessment
- Benchmarks: Shows performance regression table

### PR Comments
Fast test results are posted as PR comments with:
- Test pass/fail status
- Coverage percentages
- Link to full workflow run
- Note about full suite running nightly

## Migration Notes

### Changed Job Names
- `tests` → `fast-unit-tests` (more descriptive)

### New Jobs
- `full-test-suite` (enforces 98% coverage)

### Removed from PR Gates
- Property-based tests (moved to full suite)
- E2E tests (replaced with smoke tests)
- Heavy benchmarks (nightly only)

## Troubleshooting

### PR is blocked but unsure why
Check the fast gates: lint, fast-unit-tests, security-fast, web-lint

### Want to run heavy tests on a PR
Trigger manually via workflow_dispatch or push to main

### Cache issues
Cache keys include hash of lock files. If deps change, cache invalidates automatically.

### Coverage below 98%
This only fails in `full-test-suite` (heavy job). Fast tests report coverage for information only.

## Future Enhancements

Planned improvements:
- [ ] Parallel test execution in fast-unit-tests (pytest-xdist)
- [ ] Test result database for historical tracking
- [ ] Auto-stabilization of flaky tests
- [ ] Progressive rollout gates (canary tests)
