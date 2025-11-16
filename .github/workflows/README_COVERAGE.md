# Test Coverage Configuration Guide

This document explains how to configure and use the test coverage workflows in the TradePulse repository.

## Overview

**PRIMARY WORKFLOW:** Test coverage for PRs is enforced by `.github/workflows/tests.yml`

The tests.yml workflow enforces test coverage requirements (98% line coverage, 90% branch coverage) on all pull requests. Additional validation with mutation testing runs on the main branch via `ci.yml`.

### Workflow Split (As of 2025-11-16)

- **`tests.yml`**: Primary PR quality gate - runs linting, type checking, unit/integration tests with coverage
- **`ci.yml`**: Post-merge validation - runs sharded coverage and mutation testing on main branch only

## Quick Reference / Швидкий довідник

| Завдання | Що робить / користь | Приклад реалізації |
| --- | --- | --- |
| **Покриття коду / Code Coverage** | Генерує `coverage.xml`, підсвічує просідання покриття безпосередньо у PR та живить дашборди Codecov/Coveralls для довгострокового моніторингу. | `pytest --cov=core --cov=backtest --cov=execution --cov-report=term-missing --cov-report=xml`; завантаження `coverage.xml` у Codecov (`codecov/codecov-action`) або Coveralls (`coverallsapp/github-action`). |

## Configuration

### Coverage Thresholds

Current coverage thresholds:
- **Line Coverage:** 98% (strictly enforced)
- **Branch Coverage:** 90% (strictly enforced)

To change these thresholds:

1. **For PR Coverage (tests.yml):**
   - Open `.github/workflows/tests.yml`
   - Locate the `pytest` command in the "Run unit and integration tests with coverage" step
   - Modify the `--cov-fail-under` parameter (currently 98)
   - Update the branch coverage check in the "Publish coverage summary" step (currently 90)

2. **For Main Branch Coverage (ci.yml):**
   - Open `.github/workflows/ci.yml`
   - Modify the "Enforce global coverage threshold" step (currently 98%)
   - Update `configs/quality/critical_surface.toml` for module-specific thresholds

### Coverage Scope

Coverage is measured for critical business logic packages:
- `core` - Core trading logic
- `backtest` - Backtesting engine
- `execution` - Order execution system

To measure coverage for different targets:

1. **For PR Coverage (tests.yml):**
   ```yaml
   pytest tests/ \
     --cov=core --cov=backtest --cov=execution \
     --cov-branch \
     --cov-fail-under=98
   ```

2. **For Main Branch Coverage (ci.yml):**
   ```yaml
   pytest tests/ \
     --cov=core \
     --cov=backtest \
     --cov=execution \
     --cov-config=configs/quality/critical_surface.coveragerc
   ```

### Publishing Coverage Artifacts

The workflow uploads `coverage.xml` using `actions/upload-artifact@v4`. You can download the artifact from the workflow run summary in GitHub Actions. If you need additional formats (for example, HTML), extend the step to include the generated paths.

You can also configure coverage settings in `.coveragerc` file in the repository root.

## Codecov Integration

### For Public Repositories

Codecov works automatically for public repositories without requiring a token. The workflow will upload coverage reports to Codecov for tracking coverage trends over time.

### For Private Repositories

To enable Codecov for private repositories:

1. Go to [Codecov](https://codecov.io/) and sign in with your GitHub account
2. Add your repository to Codecov
3. Copy the repository upload token from Codecov settings
4. Add the token to your GitHub repository secrets:
   - Go to your repository's **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Name: `CODECOV_TOKEN`
   - Value: Paste the token from Codecov
   - Click **Add secret**

The workflow is configured with `fail_ci_if_error: true`, which means it will fail if Codecov upload fails (useful for catching configuration issues).

## Branch Protection

To make test coverage a required check before merging pull requests:

1. Go to your repository's **Settings** → **Branches**
2. Under "Branch protection rules", click **Add rule** or edit the existing rule for `main`
3. Enter `main` as the branch name pattern (if creating a new rule)
4. Check **Require status checks to pass before merging**
5. Check **Require branches to be up to date before merging**
6. In the search box, find and select:
   - `Tests (Python 3.11)` - Main test suite with coverage from tests.yml
   - `Lint & Type Check (Python 3.11)` - Code quality checks from tests.yml
   - `Merge Guard Quality Check` - Final validation from merge-guard.yml
7. (Optional but recommended) Check **Require a pull request before merging**
8. Click **Create** or **Save changes**

This ensures that:
- All tests must pass
- Coverage must meet the 98% threshold
- Branch coverage must meet the 90% threshold
- All linting and type checks pass
- Pull requests cannot be merged until these checks pass

## Workflow Triggers

### tests.yml (Primary PR Coverage)
Runs automatically on:
- **Pull requests** to any branch
- **Pushes** to main/develop branches

### ci.yml (Post-Merge Validation)
Runs automatically on:
- **Pushes** to the `main` branch only (PRs disabled as of 2025-11-16)

This split ensures:
- Fast feedback on PRs with essential coverage checks (tests.yml)
- Comprehensive validation with sharded coverage and mutation testing after merge (ci.yml)

## Viewing Coverage Reports

### In GitHub Actions

1. Go to the **Actions** tab in your repository
2. Click on a workflow run
3. Expand the "Run tests with coverage" step to see the coverage report in the logs

### On Codecov

1. Visit your repository on [Codecov](https://codecov.io/)
2. View detailed coverage reports, trends, and file-level coverage
3. See coverage changes in pull request comments (automatically posted by Codecov)

## Troubleshooting

### Coverage Below Threshold

If the workflow fails due to low coverage:
1. Check which files/functions are not covered in the test output
2. Add tests to cover the missing code
3. Push your changes to re-run the workflow

### Codecov Upload Fails

If Codecov upload fails:
- For private repos: Ensure `CODECOV_TOKEN` secret is correctly configured
- For public repos: Check Codecov service status
- Verify the `coverage.xml` file is being generated correctly

### Python Version Compatibility

The workflow tests against Python 3.10 and 3.11. If your code requires a different version:
1. Edit the `matrix.python-version` in `.github/workflows/ci.yml`
2. Update the branch protection rules to match the new Python versions
