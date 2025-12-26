# TradePulse Packaging & Import Policy

## Canonical Import Namespace

**The canonical public import namespace for TradePulse is `tradepulse.*`.**

```python
# ✅ Correct - Canonical imports
from tradepulse.risk import RiskEngine
from tradepulse.analytics import MarketAnalyzer
import tradepulse

# ❌ Deprecated - Do not use in new code
from src.tradepulse import ...  # Not recommended
import src.tradepulse  # Not recommended
```

### Import Reality Check (current)

- `tradepulse.*` is canonical and installed; prefer it for all new code.
- `src.tradepulse.*` exists only as a legacy mirror to avoid breaking older imports.
- `core.*` stays internal/legacy; serotonin canonical implementation lives in `core.neuro.serotonin`.
- New features should target `tradepulse.*` while maintaining shims for `src.tradepulse.*`.
- Expect future clean-up to remove `src.*` once consumers migrate.

## Directory Structure

```
TradePulse/
├── tradepulse/          # ✅ Canonical package (installed)
│   ├── __init__.py
│   ├── risk/
│   ├── analytics/
│   └── neural_controller/
├── src/                 # ⚠️ Source layout container (NOT installed as package)
│   ├── tradepulse/      # Internal development modules
│   ├── admin/
│   ├── data/
│   └── ...
├── core/                # ✅ Core modules (installed)
├── backtest/            # ✅ Backtest engine (installed)
├── execution/           # ✅ Execution layer (installed)
└── pyproject.toml
```

## Why This Structure?

### Problem Solved

Previously, `src/__init__.py` made `src` an importable Python package, creating ambiguity:

- Two competing import roots: `tradepulse.*` vs `src.tradepulse.*`
- Packaging could accidentally ship both
- Tests and CI could import different code paths

### Solution

1. **`src.tradepulse.*` is kept only as a compatibility shim**
   - Included in packaging to keep legacy imports working
   - Do not add new `src.*` entry points

2. **`tradepulse.*` is the canonical namespace**
   - Installed as the public API
   - Documented and supported
   - Versioned and tested

## For Developers

### During Development

In development mode (`pip install -e .`), you may still import from `src.*` due to PYTHONPATH. However:

- **Do not add new `from src.*` imports** in production code
- Use canonical `tradepulse.*` imports for new code
- Existing `src.*` imports will be migrated over time

### After Installation

After running `pip install .` (non-editable), `tradepulse.*` is installed as the
public API. Legacy `src.tradepulse.*` shims are still packaged for backward
compatibility, but should be treated as deprecated:

```python
>>> import tradepulse
>>> tradepulse.__file__
'/path/to/site-packages/tradepulse/__init__.py'
```

## Migration Guide

### For Internal Code

If you have code using `src.*` imports:

```python
# Before (deprecated)
from src.audit.audit_logger import AuditLogger
from src.risk.risk_manager import RiskManagerFacade

# After (preferred)
# Option 1: Use application-level imports if available
from application.logging import AuditLogger
from application.risk import RiskManagerFacade

# Option 2: Keep src.* for now, but document as internal
# (will be migrated in future refactor)
```

### For External Users

If you're importing TradePulse as a library:

```python
# Always use:
from tradepulse import ...
from tradepulse.risk import ...
from tradepulse.analytics import ...

# Never use:
from src.tradepulse import ...  # Will not work after install
```

## Verification

Run namespace verification tests:

```bash
pytest tests/packaging/test_namespace.py -v
```

Verify installation:

```bash
# Build
python -m build

# Install in fresh venv
python -m venv /tmp/test-venv
source /tmp/test-venv/bin/activate
pip install dist/*.whl

# Verify
python -c "import tradepulse; print(tradepulse.__file__)"
python -c "import src"  # Should raise ModuleNotFoundError
```

## Configuration

The packaging configuration is in `pyproject.toml`:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = [
    "tradepulse",
    "tradepulse.*",
    # ... other packages ...
    "src",
    "src.*",  # legacy shim to keep existing imports alive
]
exclude = ["tests", "tests.*", "docs", "docs.*"]
```

Key points:
- Canonical namespace is `tradepulse.*`
- `src.*` is packaged only as a legacy mirror
- Tests and docs are excluded from distribution

## Related Documentation

- [Architecture Overview](../ARCHITECTURE.md)
- [Contributing Guide](../../CONTRIBUTING.md)
- [Development Setup](../../SETUP.md)
