# Running the Release Gate Locally

This guide shows you how to reproduce the exact same checks that run in `.github/workflows/release-gate.yml` on your local machine.

## Prerequisites

- Python 3.11 or 3.12
- Git clone of TradePulse repository
- Terminal/shell access

## Quick Start (5 minutes)

```bash
# 1. Navigate to repository
cd /path/to/TradePulse

# 2. Create virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
python -m pip install --upgrade pip setuptools wheel
pip install -c constraints/security.txt -r requirements.txt
pip install -c constraints/security.txt -r requirements-dev.txt

# 4. Run the full release gate
make test  # Uses Makefile shortcut

# OR run individual components:
```

## Step-by-Step Breakdown

### Step 1: Install Dependencies

```bash
# Upgrade pip and build tools
python -m pip install --upgrade pip setuptools wheel

# Install runtime dependencies
pip install -c constraints/security.txt -r requirements.txt

# Install development dependencies (linters, test tools)
pip install -c constraints/security.txt -r requirements-dev.txt
```

**What this does:**
- Installs all packages needed to run the code
- Installs linters (ruff, black, mypy)
- Installs test framework (pytest)
- Respects security constraints in `constraints/security.txt`

**Expected time:** 2-3 minutes

### Step 2: Run Linting

```bash
# Fast linter (catches most issues)
python -m ruff check .

# Formatter check (code style)
python -m black --check .

# Optional: Auto-fix formatting
python -m black .
```

**What this checks:**
- Code style violations
- Common Python errors
- Import ordering
- Unused imports/variables

**Expected time:** 10-30 seconds

**Common fixes:**
```bash
# Auto-fix most linting issues
python -m ruff check --fix .

# Auto-format code
python -m black .
```

### Step 3: Run Type Checking

```bash
# Type check core modules only (fast)
python -m mypy core/ backtest/ execution/ src/tradepulse/

# Optional: Full type check (slower, may have more errors)
python -m mypy .
```

**What this checks:**
- Type annotations are correct
- Function signatures match usage
- No type mismatches

**Expected time:** 30-60 seconds

**Common issues:**
- Missing type hints (add `: Type` annotations)
- Type mismatches (fix the types or add `# type: ignore`)
- Import errors (check module structure)

### Step 4: Run Core Tests

```bash
# Run the exact same tests as release-gate.yml
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

**What this runs:**
- Unit tests for backtest engine
- Unit tests for execution system
- Integration tests for backtest
- Core runtime tests
- **Excludes:** slow, heavy, nightly, and flaky tests

**Expected time:** 2-5 minutes

**Verbose output (if needed):**
```bash
# Remove --quiet for detailed output
pytest \
  tests/unit/backtest/ \
  tests/unit/execution/ \
  tests/execution/ \
  tests/integration/test_backtest.py \
  tests/core/ \
  --ignore=tests/core/agent/ \
  --ignore=tests/core/orchestrator/ \
  -m "not slow and not heavy_math and not nightly and not flaky" \
  -v
```

**Run specific test file:**
```bash
pytest tests/unit/backtest/test_example.py -v
```

**Run specific test function:**
```bash
pytest tests/unit/backtest/test_example.py::test_specific_function -v
```

## Makefile Shortcuts

The repository provides convenient Makefile targets:

```bash
# Install dependencies
make install

# Run core tests (fast)
make test

# Run linting
make lint

# Auto-format code
make format

# Security audit
make audit

# Clean cache files
make clean
```

## Troubleshooting

### Tests Fail Locally but Pass in CI

**Possible causes:**
1. Different Python version (CI uses 3.11, check yours: `python --version`)
2. Stale cache files (run: `make clean`)
3. Missing dependencies (run: `make install`)
4. Different working directory (run from repo root)

**Fix:**
```bash
make clean
make install
make test
```

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'tradepulse'`

**Fix:** Install in development mode:
```bash
pip install -e .
```

### Type Check Errors

**Error:** `mypy` finds many errors

**Fix:** Core modules are type-checked in release gate. Other modules may have type issues but won't block merge:
```bash
# Only check what release-gate checks
python -m mypy core/ backtest/ execution/ src/tradepulse/
```

### Slow Tests

**Problem:** Tests take > 5 minutes

**Causes:**
1. Running all tests (including slow ones)
2. Not using pytest markers

**Fix:** Use the exact release-gate command with markers:
```bash
pytest \
  tests/unit/backtest/ \
  tests/unit/execution/ \
  tests/execution/ \
  tests/integration/test_backtest.py \
  tests/core/ \
  --ignore=tests/core/agent/ \
  --ignore=tests/core/orchestrator/ \
  -m "not slow and not heavy_math and not nightly and not flaky"
```

### Flaky Tests

**Problem:** Tests pass sometimes, fail other times

**Solution:** Mark as flaky so they don't block CI:
```python
import pytest

@pytest.mark.flaky
def test_sometimes_fails():
    # This test won't run in release gate
    pass
```

## What's NOT Checked Locally (Experimental)

These are NOT required for the release gate and can be run optionally:

### Mutation Testing (90 minutes)
```bash
# NOT required for release gate, very slow
mutmut run --paths-to-mutate=core,backtest,execution --tests-dir=tests
python -m tools.mutation.kill_rate_guard --threshold=0.9
```

### Performance Regression
```bash
# NOT required for release gate
pytest tests/performance --benchmark-only
```

### Load Testing
```bash
# NOT required for release gate
# Requires additional setup (Locust, services)
```

### Heavy E2E Tests
```bash
# NOT required for release gate
pytest tests/e2e/ -m "slow"
```

## CI vs Local Differences

| Aspect | CI (release-gate.yml) | Local (this guide) |
|--------|----------------------|-------------------|
| Python version | 3.11 | Your version (should be 3.11 or 3.12) |
| Environment | Ubuntu latest | Your OS |
| Cache | GitHub Actions cache | Local cache |
| Duration | ~10-15 min | ~5-10 min (after first install) |
| Required for merge | ✅ Yes | ⚠️ Recommended before push |

## Pre-Push Checklist

Before pushing code, run:

```bash
# 1. Auto-format
make format

# 2. Run linting
make lint

# 3. Run tests
make test

# 4. Check git status
git status

# 5. If all pass, push
git push origin your-branch
```

## When to Skip Local Testing

You can skip local testing if:
- ✅ Only changing documentation (`.md` files)
- ✅ Only changing non-code files (configs, data files)
- ✅ Making very small changes (1-2 lines)

CI will still run, but failures are less likely.

## Getting Help

- **Release gate is red:** Check PR comments for specific failure
- **Tests fail locally:** See "Troubleshooting" section above
- **Need more details:** See `.github/workflows/release-gate.yml` for exact CI commands
- **Questions:** Consult `docs/RELEASE_GATES.md` for policy details

---

**Last Updated:** 2025-12-09 - Initial version for minimal release gate