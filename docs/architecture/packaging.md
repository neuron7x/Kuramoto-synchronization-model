# GeoSync Packaging & Import Policy

## Canonical Import Namespace

**The canonical public import namespace for GeoSync is `geosync.*`.**

```python
# ✅ Correct - Canonical imports
from geosync.risk import RiskEngine
from geosync.analytics import MarketAnalyzer
import geosync

# ❌ Deprecated - Do not use in new code
from src.geosync import ...  # Not recommended
import src.geosync  # Not recommended
```

### Import Reality Check (current)

- `geosync.*` is canonical and installed; prefer it for all new code.
- `src.geosync.*` exists only as a legacy mirror to avoid breaking older imports.
- `core.*` stays internal/legacy; serotonin canonical implementation lives in `core.neuro.serotonin`.
- New features should target `geosync.*` while maintaining shims for `src.geosync.*`.
- Expect future clean-up to remove `src.*` once consumers migrate.

## Directory Structure

```
GeoSync/
├── geosync/          # ✅ Canonical package (installed)
│   ├── __init__.py
│   ├── risk/
│   ├── analytics/
│   └── neural_controller/
├── src/                 # ⚠️ Source layout container (NOT installed as package)
│   ├── geosync/      # Internal development modules
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

- Two competing import roots: `geosync.*` vs `src.geosync.*`
- Packaging could accidentally ship both
- Tests and CI could import different code paths

### Solution

1. **`src.geosync.*` is kept only as a compatibility shim**
   - Included in packaging to keep legacy imports working
   - Do not add new `src.*` entry points

2. **`geosync.*` is the canonical namespace**
   - Installed as the public API
   - Documented and supported
   - Versioned and tested

## For Developers

### During Development

In development mode (`pip install -e .`), you may still import from `src.*` due to PYTHONPATH. However:

- **Do not add new `from src.*` imports** in production code
- Use canonical `geosync.*` imports for new code
- Existing `src.*` imports will be migrated over time

### After Installation

After running `pip install .` (non-editable), `geosync.*` is installed as the
public API. Legacy `src.geosync.*` shims are still packaged for backward
compatibility, but should be treated as deprecated:

```python
>>> import geosync
>>> geosync.__file__
'/path/to/site-packages/geosync/__init__.py'
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

If you're importing GeoSync as a library:

```python
# Always use:
from geosync import ...
from geosync.risk import ...
from geosync.analytics import ...

# Never use:
from src.geosync import ...  # Will not work after install
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
python -c "import geosync; print(geosync.__file__)"
python -c "import src"  # Should raise ModuleNotFoundError
```

## Configuration

The packaging configuration is in `pyproject.toml`:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = [
    "geosync",
    "geosync.*",
    # ... other packages ...
    "src",
    "src.*",  # legacy shim to keep existing imports alive
]
exclude = ["tests", "tests.*", "docs", "docs.*"]
```

Key points:
- Canonical namespace is `geosync.*`
- `src.*` is packaged only as a legacy mirror
- Tests and docs are excluded from distribution

## Related Documentation

- [Architecture Overview](../ARCHITECTURE.md)
- [Contributing Guide](../../CONTRIBUTING.md)
- [Development Setup](../operations/SETUP.md)
