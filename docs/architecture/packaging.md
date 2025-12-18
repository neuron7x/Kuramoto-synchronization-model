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

1. **`src/` is a source directory, not a package**
   - `src/` is explicitly excluded from installed packages
   - Contains internal development modules
   - NOT intended for external API use

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

After running `pip install .` (non-editable), the `src` package is **not available**:

```python
>>> import src
ModuleNotFoundError: No module named 'src'

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
    # ... other packages
]
exclude = ["tests", "tests.*", "docs", "docs.*", "src", "src.*"]
```

Key points:
- `src` and `src.*` are **explicitly excluded**
- Only canonical packages are included
- Tests and docs are excluded from distribution

## Related Documentation

- [Architecture Overview](../ARCHITECTURE.md)
- [Contributing Guide](../../CONTRIBUTING.md)
- [Development Setup](../../SETUP.md)
