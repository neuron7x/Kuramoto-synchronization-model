# Reality Map — GeoSync v0.1.0

## Product Identity
- **Name**: GeoSync
- **Version**: 0.1.0 (pre-release)
- **Package name**: `geosync` (PyPI-style)
- **License**: MIT

## Canonical Namespace
- **Canonical**: `geosync.*` lives in `src/geosync/`
- **Active top-level packages**: `core`, `backtest`, `execution`, `analytics`, `modules`, `geosync`
- **Legacy shim**: `core/__init__.py` says "Legacy package shim" but golden path imports from `core.*` directly
- **Reality**: Golden path uses `core.*` and `backtest.*` as primary imports, NOT `src.geosync.*`
- **Package discovery**: `pyproject.toml` uses `where=["."]` (flat layout), includes both `core` and `geosync`

## Canonical Entrypoints
1. `examples/quick_start.py` — primary demo (synthetic data + Kuramoto-Ricci analysis)
2. `make golden-path` — full workflow: data gen → analysis → backtest integration test
3. `make test` — fast PR gate test suite
4. `python -m build` — produces wheel + sdist

## Architecture Drift (Observed)
- Repo name: "Kuramoto-synchronization-model-main" vs product name "GeoSync"
- `core/` labeled "legacy" in its __init__.py but is the primary import surface for golden path
- `src/geosync/` is `__CANONICAL__ = True` but not used by examples or tests
- Two `geosync/` directories: top-level (neural_controller, risk, data_quality) and `src/geosync/`
- Mixed use of `PYTHONPATH=.` (Makefile) and `pythonpath = .` (pytest.ini)

## Likely Blockers (Pre-baseline)
- Heavy dependencies: torch (2.9.1+cu128), numpy>=2.3.3, ~60 direct deps
- CUDA-dependent torch wheel on CPU-only machines
- `--maxfail=1` in pytest.ini stops suite at first collection error
- No git repo (repo was extracted, not cloned)

## Test Surface
- 670+ test files across tests/, core/neuro/tests/
- Golden path tests: `tests/integration/test_golden_path_backtest.py` (21 tests)
- Fast gate: `pytest tests/ -m "not slow and not heavy_math and not nightly and not flaky"`

## Build Surface
- `python -m build` via setuptools + setuptools_scm
- Produces: `geosync-0.1.0-py3-none-any.whl` (~2MB), `geosync-0.1.0.tar.gz` (~1.7MB)
- Lock files: `requirements.lock`, `requirements-dev.lock` (pip-compile generated)
- Security constraints: `constraints/security.txt`
