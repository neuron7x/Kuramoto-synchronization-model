# TradePulse Quality Standards

## Overview

This document defines the code quality standards for the TradePulse project, ensuring consistent, maintainable, and production-ready code across all contributions.

## Code Quality Metrics

### Current Status (2025-11-17)

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Linting Errors | < 100 | 79 | ✅ Pass |
| Test Pass Rate | > 95% | 99.7% (375/376) | ✅ Pass |
| Code Formatting | 100% | 100% | ✅ Pass |
| Type Hint Coverage | > 80% | 75% | 🔄 In Progress |
| Test Coverage | > 98% | TBD | 📊 To Measure |

### Quality Gates

All PRs must meet these criteria before merging:

1. **Linting**: Zero new linting errors introduced
2. **Tests**: All existing tests must pass
3. **Formatting**: Code must be formatted with Black
4. **Type Hints**: New public APIs must have type hints
5. **Documentation**: New features must be documented

## Coding Standards

### 1. Code Formatting

**Tool**: [Black](https://github.com/psf/black)

**Configuration** (`pyproject.toml`):
```toml
[tool.black]
line-length = 100
target-version = ['py311', 'py312']
extend-exclude = 'docs/notebooks'
```

**Usage**:
```bash
# Format all code
black .

# Check formatting without modifying
black --check .
```

**Rationale**: Automated formatting eliminates debates about style and ensures consistency.

### 2. Import Organization

**Tool**: [Ruff](https://github.com/astral-sh/ruff) (integrated)

**Standard Order**:
1. Standard library imports
2. Third-party imports
3. Local application imports
4. Relative imports

**Example**:
```python
# Standard library
from typing import Any, Dict, List
import os
import sys

# Third-party
import numpy as np
import pandas as pd
from pydantic import BaseModel

# Local application
from core.indicators import KuramotoIndicator
from core.data import MarketDataPoint

# Relative
from .models import Signal
```

**Auto-fix**:
```bash
ruff check --fix --select I .
```

### 3. Linting Rules

**Tool**: [Ruff](https://github.com/astral-sh/ruff)

**Configuration** (`pyproject.toml`):
```toml
[tool.ruff]
line-length = 100
extend-exclude = ["docs/notebooks"]

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
ignore = ["E203", "E501"]
```

**Key Rules**:
- **F401**: No unused imports
- **F841**: No unused variables
- **E402**: Module imports at top of file (with exceptions)
- **W291/W293**: No trailing whitespace
- **I001**: Sorted imports

**Intentional Exceptions**:

Some violations are intentional design choices and are acceptable:

1. **E402 (Module imports not at top)**: For lazy loading
   ```python
   # Acceptable pattern
   try:
       import heavy_optional_library
   except ImportError:
       heavy_optional_library = None
   ```

2. **F821 (Undefined names in type hints)**: For forward references
   ```python
   # Acceptable pattern
   from __future__ import annotations
   
   def process(data: "MarketDataService") -> None:
       from application.services import MarketDataService
       # Implementation
   ```

3. **F401 (Unused imports)**: For type checking only
   ```python
   # Acceptable pattern
   from typing import TYPE_CHECKING
   
   if TYPE_CHECKING:
       from expensive_module import ExpensiveType
   ```

### 4. Type Hints

**Tool**: [mypy](https://mypy-lang.org)

**Configuration** (`mypy.ini`):
```ini
[mypy]
ignore_missing_imports = true
explicit_package_bases = true
plugins = numpy.typing.mypy_plugin
```

**Standards**:

1. **All public APIs must have type hints**:
   ```python
   # Good
   def calculate_signal(prices: np.ndarray, window: int = 20) -> float:
       return float(np.mean(prices[-window:]))
   
   # Bad
   def calculate_signal(prices, window=20):
       return float(np.mean(prices[-window:]))
   ```

2. **Use specific types, not Any**:
   ```python
   # Good
   def process_data(data: pd.DataFrame) -> Dict[str, float]:
       return {"mean": data.mean(), "std": data.std()}
   
   # Bad
   def process_data(data: Any) -> Any:
       return {"mean": data.mean(), "std": data.std()}
   ```

3. **Use NumPy 2.0 compatible types**:
   ```python
   # Good (NumPy 2.0+)
   from numpy.typing import NDArray
   import numpy as np
   
   def calculate(data: NDArray[np.float64]) -> np.float64:
       return np.mean(data)
   
   # Bad (deprecated in NumPy 2.0)
   def calculate(data: np.ndarray) -> np.float_:
       return np.mean(data)
   ```

4. **Forward references for circular imports**:
   ```python
   from __future__ import annotations
   
   class Node:
       def __init__(self, parent: Node | None = None):
           self.parent = parent
   ```

### 5. Documentation

**Standards**:

1. **Module-level docstrings**:
   ```python
   """Market data ingestion and validation.
   
   This module provides robust market data ingestion with:
   - Automatic retry logic
   - Data validation
   - Gap detection and filling
   """
   ```

2. **Function/method docstrings** (Google style):
   ```python
   def calculate_sharpe_ratio(
       returns: pd.Series,
       risk_free_rate: float = 0.0,
       periods_per_year: int = 252
   ) -> float:
       """Calculate annualized Sharpe ratio.
       
       Args:
           returns: Time series of returns
           risk_free_rate: Annual risk-free rate (default: 0.0)
           periods_per_year: Number of periods per year (default: 252 for daily)
       
       Returns:
           Annualized Sharpe ratio
       
       Raises:
           ValueError: If returns is empty or all NaN
       
       Example:
           >>> returns = pd.Series([0.01, -0.02, 0.03, 0.01])
           >>> sharpe = calculate_sharpe_ratio(returns)
           >>> print(f"Sharpe: {sharpe:.2f}")
       """
       if returns.empty or returns.isna().all():
           raise ValueError("Returns series cannot be empty or all NaN")
       
       excess_returns = returns - risk_free_rate / periods_per_year
       return np.sqrt(periods_per_year) * excess_returns.mean() / excess_returns.std()
   ```

3. **Class docstrings**:
   ```python
   class KuramotoIndicator:
       """Kuramoto synchronization-based market indicator.
       
       This indicator uses the Kuramoto model of coupled oscillators to detect
       market synchronization and potential regime changes.
       
       Attributes:
           window: Lookback window for calculation
           coupling: Coupling strength between oscillators
           n_oscillators: Number of oscillators in the ensemble
       
       Example:
           >>> indicator = KuramotoIndicator(window=80, coupling=0.9)
           >>> prices = np.array([100, 101, 102, 103])
           >>> order_param = indicator.compute(prices)
       """
   ```

## Testing Standards

### 1. Test Organization

```
tests/
├── unit/           # Fast, isolated unit tests
├── integration/    # Integration tests with external dependencies
├── e2e/           # End-to-end tests
├── property/      # Property-based tests with Hypothesis
└── performance/   # Performance benchmarks
```

### 2. Test Naming

**Convention**: `test_<unit>_<scenario>_<expected_result>`

```python
# Good
def test_kuramoto_indicator_with_trending_data_returns_high_synchronization():
    indicator = KuramotoIndicator(window=20)
    trending_prices = np.linspace(100, 110, 50)
    order = indicator.compute(trending_prices)
    assert order > 0.8

# Bad
def test_kuramoto():
    # unclear what's being tested
```

### 3. Test Structure

**Use AAA pattern**: Arrange, Act, Assert

```python
def test_position_sizer_respects_max_position_size():
    # Arrange
    sizer = PositionSizer(max_position_size=10000)
    signal = Signal(symbol="BTC", strength=1.0)
    
    # Act
    position = sizer.calculate_position(signal, capital=100000)
    
    # Assert
    assert position.size <= 10000
```

### 4. Test Coverage

**Target**: 98% for core modules

**Measure**:
```bash
pytest --cov=core --cov=backtest --cov=execution --cov-report=html
```

**Focus areas**:
- All public APIs
- Edge cases and error conditions
- Integration points
- Complex algorithms

## Dependency Management

### 1. Version Pinning

**Strategy**: Use `requirements.lock` for reproducible builds

```bash
# Generate lock file
pip-compile requirements.in --output-file=requirements.lock

# Install from lock file
pip install -r requirements.lock
```

### 2. Dependency Updates

**Process**:
1. Review security advisories
2. Test updates in isolated environment
3. Run full test suite
4. Update lock file
5. Create PR with changes

### 3. Optional Dependencies

**Pattern**: Use extras for optional features

```toml
[project.optional-dependencies]
gpu = ["cupy>=13.6.0"]
feature_store = ["polars>=1.34.0", "pyarrow>=21.0.0"]
```

**Installation**:
```bash
pip install tradepulse[gpu,feature_store]
```

## Git Workflow

### 1. Branch Naming

**Convention**: `<type>/<short-description>`

**Types**:
- `feature/` - New features
- `fix/` - Bug fixes
- `refactor/` - Code refactoring
- `docs/` - Documentation updates
- `test/` - Test improvements
- `chore/` - Maintenance tasks

**Examples**:
- `feature/add-macd-indicator`
- `fix/numpy-compatibility`
- `refactor/simplify-position-sizer`

### 2. Commit Messages

**Format**: `<type>: <subject>`

**Types**: feat, fix, docs, style, refactor, test, chore

**Examples**:
```
feat: Add MACD indicator with configurable parameters
fix: Handle edge case in position sizing
docs: Update installation guide with GPU requirements
refactor: Simplify indicator normalization logic
test: Add property tests for Sharpe ratio calculation
```

### 3. Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Refactoring
- [ ] Documentation
- [ ] Testing

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing performed

## Quality Checklist
- [ ] Code formatted with Black
- [ ] No new linting errors
- [ ] Type hints added for new code
- [ ] Documentation updated
```

## Pre-commit Hooks

**Install**:
```bash
pip install pre-commit
pre-commit install
```

**Configuration** (`.pre-commit-config.yaml`):
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 25.11.0
    hooks:
      - id: black
        language_version: python3.12

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.5
    hooks:
      - id: ruff
        args: [--fix, --select, "I,F401,F841,W291,W293"]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.18.2
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: [--ignore-missing-imports]
```

## IDE Configuration

### VS Code

**`.vscode/settings.json`**:
```json
{
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length", "100"],
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.linting.mypyEnabled": true,
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
```

### PyCharm

**Settings → Editor → Code Style → Python**:
- Line length: 100
- Use Black formatter: Yes

**Settings → Tools → External Tools**:
- Add Ruff as external tool
- Add mypy as external tool

## Performance Standards

### 1. Algorithm Complexity

**Guidelines**:
- O(n) preferred for data processing
- O(n log n) acceptable for sorting/searching
- O(n²) requires justification

**Document complexity**:
```python
def calculate_correlation_matrix(data: pd.DataFrame) -> np.ndarray:
    """Calculate pairwise correlation matrix.
    
    Time complexity: O(n² * m) where n is number of assets, m is number of samples
    Space complexity: O(n²)
    
    Note: For n > 1000, consider using sparse representation.
    """
    return data.corr().values
```

### 2. Memory Optimization

**Guidelines**:
- Use generators for large datasets
- Stream data when possible
- Profile memory usage for critical paths

**Example**:
```python
# Good: Generator for large datasets
def stream_market_data(symbols: List[str]) -> Iterator[MarketData]:
    for symbol in symbols:
        yield fetch_data(symbol)

# Bad: Load everything into memory
def load_all_market_data(symbols: List[str]) -> List[MarketData]:
    return [fetch_data(symbol) for symbol in symbols]
```

## Security Standards

### 1. Secret Management

**Never commit**:
- API keys
- Passwords
- Private keys
- Connection strings

**Use**:
- Environment variables
- HashiCorp Vault
- AWS Secrets Manager

**Pattern**:
```python
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str
    database_url: str
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### 2. Input Validation

**Always validate external input**:
```python
from pydantic import BaseModel, Field, validator

class OrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float = Field(..., gt=0)
    
    @validator('symbol')
    def validate_symbol(cls, v):
        if not v.isalnum():
            raise ValueError('Symbol must be alphanumeric')
        return v.upper()
```

## Continuous Improvement

### 1. Quality Metrics Dashboard

Track and visualize:
- Linting error trends
- Test coverage over time
- Type hint coverage
- Code complexity metrics

### 2. Regular Reviews

**Monthly**:
- Review quality metrics
- Identify improvement areas
- Update standards as needed

**Quarterly**:
- Comprehensive codebase audit
- Tool and framework updates
- Process improvements

### 3. Team Education

**Onboarding**:
- Share this document with new team members
- Pair programming sessions
- Code review feedback

**Continuous Learning**:
- Tech talks on best practices
- Share articles and resources
- Celebrate quality improvements

## References

### Standards
- [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PEP 484 - Type Hints](https://peps.python.org/pep-0484/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

### Tools
- [Black - Code Formatter](https://github.com/psf/black)
- [Ruff - Fast Python Linter](https://github.com/astral-sh/ruff)
- [mypy - Static Type Checker](https://mypy-lang.org)
- [pytest - Testing Framework](https://pytest.org)

### Related Documentation
- [ADR-001: Code Quality Improvement](docs/architecture/decisions/ADR-001-code-quality-architecture-improvement.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Testing Guide](TESTING.md)

---

**Document Owner**: Engineering Leadership  
**Last Updated**: 2025-11-17  
**Next Review**: 2025-12-17
