# TradePulse — Working Stack Runbook

Verified 2026-03-28 on Python 3.12.3, Linux (Ubuntu).

## What This Repo Is

TradePulse v0.1.0 — algorithmic trading framework with geometric market indicators
(Kuramoto synchronization, Ricci curvature, entropy production, neuro-inspired controllers).

## Canonical Product Identity

- **Package**: `tradepulse`
- **Primary import surface**: `core.*`, `backtest.*`, `execution.*`, `analytics.*`
- **Build artifact**: `tradepulse-0.1.0-py3-none-any.whl`

## Bootstrap (Fresh Environment)

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Upgrade packaging basics
python -m pip install --upgrade pip setuptools wheel

# 3. Install runtime dependencies
pip install -c constraints/security.txt -r requirements.lock

# 4. (Optional) Install dev/test dependencies
pip install -c constraints/security.txt -r requirements-dev.lock
```

Requirements: Python >=3.11,<3.13. Tested on 3.12.3.

## Canonical Golden Path

```bash
# Quick demo — generates synthetic data, runs Kuramoto-Ricci analysis
PYTHONPATH=. python examples/quick_start.py --seed 42 --num-points 500

# Full golden path — data gen + analysis + backtest integration
make golden-path
```

Expected output: Market phase classification (e.g. "transition"), confidence score, entry signal.

## Verification Commands

```bash
# Golden path integration tests (21 tests, <1s)
pytest tests/integration/test_golden_path_backtest.py -v

# Fast PR gate (~6 min, ~7800 tests)
make test

# Full suite without maxfail
pytest tests/ -m "not slow and not heavy_math and not nightly and not flaky" \
  --override-ini="addopts=-ra --continue-on-collection-errors --import-mode=importlib"
```

## Build Artifact

```bash
python -m build
# Output: dist/tradepulse-0.1.0-py3-none-any.whl
#         dist/tradepulse-0.1.0.tar.gz
```

## Known Non-Blocking Gaps

1. **111 test failures** in full suite — all pre-existing, none affect golden path.
   Categories: property tests (Hypothesis), serotonin controller, GABA gate, workflow YAML tests.
2. **Namespace drift**: `core/` labeled "legacy" but is the active import surface for examples/tests.
   `src/tradepulse/` marked canonical but not used by golden path. Both coexist.
3. **Torch CUDA**: torch is installed with CUDA 12.8 support. On CPU-only machines, some
   torch-dependent test modules emit collection warnings (handled by `--continue-on-collection-errors`).
4. **Not a git repo**: The working directory is not initialized as a git repo.
   `setuptools_scm` falls back to `VERSION` file (0.1.0). Some versioning tests may fail in full suite.
5. **No live trading validation**: Execution layer is well-structured but no live exchange connectivity tested.

## Evidence

See `artifacts/working_stack/20260328T151401/` for:
- `00_reality_map.md` — repo structure analysis
- `01_baseline_commands.txt` — exact commands and results
- `02_baseline_failures.txt` — categorized test failures
- `03_changes_applied.md` — what was changed and why
- `04_final_verification.txt` — final run proof
- `05_artifacts_manifest.txt` — file listing
