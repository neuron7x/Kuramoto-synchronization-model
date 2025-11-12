# Contributing to Cortex Service

Thank you for your interest in contributing to the Cortex Service! This document provides guidelines and best practices for development.

## Development Setup

### Prerequisites

- Python 3.11 or 3.12
- pip
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse/cortex_service
```

2. Install development dependencies:
```bash
pip install -e ".[dev]"
```

3. Install pre-commit hooks (if available):
```bash
pre-commit install
```

## Code Style

### Type Annotations

All code must pass `mypy --strict` with zero errors.

```python
# Good
def compute_signal(features: Sequence[FeatureObservation], settings: SignalSettings) -> Signal:
    """Compute signal with full type annotations."""
    ...

# Bad
def compute_signal(features, settings):
    """Missing type annotations."""
    ...
```

### Docstrings

Use Google-style docstrings for all public functions, classes, and modules.

```python
def assess_risk(exposures: Iterable[Exposure], settings: RiskSettings) -> RiskAssessment:
    """Assess portfolio risk from exposures.

    Args:
        exposures: Portfolio exposures to assess
        settings: Risk computation settings

    Returns:
        Risk assessment with score, VaR, stressed VaR, and breached instruments

    Raises:
        ValidationError: If exposures are invalid
    """
    ...
```

### Formatting

Code must be formatted with Black and pass Ruff linting:

```bash
# Format code
black cortex_service/

# Check formatting
black cortex_service/ --check

# Lint code
ruff check cortex_service/

# Fix auto-fixable issues
ruff check cortex_service/ --fix
```

### Code Organization

Follow the layered architecture:

```
API Layer (api.py, schemas.py)
    ↓
Service Layer (services/)
    ↓
Domain Layer (core/, ethics/, modulation/)
    ↓
Persistence Layer (memory/, models.py)
```

**Never:**
- Import from API layer in service or domain layers
- Import from service layer in domain layer
- Put business logic directly in API endpoints

### Constants

Use centralized constants instead of magic numbers:

```python
# Good
from ..constants import ZERO_STD_THRESHOLD

if abs(self.std) <= ZERO_STD_THRESHOLD:
    ...

# Bad
if abs(self.std) <= 1e-12:
    ...
```

### Error Handling

Always use the unified error taxonomy:

```python
from ..errors import ValidationError, DatabaseError, ComputationError

# Good
if not features:
    raise ValidationError("At least one feature is required", details={"count": 0})

# Bad
if not features:
    raise ValueError("No features")  # Wrong error type

# Bad
if not features:
    raise Exception("No features")  # Generic exception
```

### Immutability

Use frozen dataclasses for domain models:

```python
# Good
@dataclass(slots=True, frozen=True)
class Signal:
    """Immutable signal representation."""
    instrument: str
    strength: float
    contributors: Sequence[str]

# Bad
@dataclass
class Signal:
    """Mutable - can lead to bugs."""
    instrument: str
    strength: float
```

## Testing

### Test Organization

Tests are organized by purpose:

- `test_signals.py`: Original API integration tests
- `test_tls_config.py`: TLS configuration tests
- `test_comprehensive.py`: Comprehensive integration/unit tests
- `test_decorators.py`: Decorator-specific tests
- `test_property.py`: Hypothesis property-based tests

### Writing Tests

1. **Unit Tests**: Test individual functions with minimal dependencies

```python
def test_signal_zero_std():
    """Test handling of zero standard deviation."""
    settings = SignalSettings()
    features = [
        FeatureObservation(
            instrument="TEST",
            name="feature1",
            value=1.0,
            mean=0.5,
            std=0.0,
            weight=1.0,
        )
    ]
    signal = compute_signal(features, settings)
    assert signal.instrument == "TEST"
    assert -1.0 <= signal.strength <= 1.0
```

2. **Integration Tests**: Test multiple components together

```python
def test_regime_cache_integration():
    """Test regime caching with database."""
    settings = _test_settings()
    engine = _sqlite_engine()
    app = create_app(settings=settings, engine=engine)
    client = TestClient(app)
    
    # First request (cache miss)
    response1 = client.post("/regime", json={...})
    
    # Second request (cache hit)
    response2 = client.post("/regime", json={...})
```

3. **Property-Based Tests**: Use Hypothesis for invariants

```python
from hypothesis import given
from hypothesis import strategies as st

@given(
    value=st.floats(min_value=-1000, max_value=1000, allow_nan=False),
    std=st.floats(min_value=0.001, max_value=100, allow_nan=False),
)
def test_signal_always_bounded(value, std):
    """Signal strength must always be in configured range."""
    settings = SignalSettings(rescale_min=-1.0, rescale_max=1.0)
    features = [FeatureObservation(..., value=value, std=std)]
    signal = compute_signal(features, settings)
    assert settings.rescale_min <= signal.strength <= settings.rescale_max
```

### Running Tests

```bash
# Run all tests
pytest cortex_service/tests/ -v

# Run with coverage
pytest cortex_service/tests/ --cov=cortex_service/app --cov-report=html

# Run specific test file
pytest cortex_service/tests/test_decorators.py -v

# Run property tests with more examples
pytest cortex_service/tests/test_property.py --hypothesis-show-statistics
```

### Coverage Requirements

- **Target**: >=95% coverage
- **Current**: 87% (excluding entrypoints)
- New code should have >=90% coverage
- Critical paths (signal, risk, regime) must have >=95% coverage

## Pull Request Process

1. **Create a Feature Branch**
```bash
git checkout -b feature/your-feature-name
```

2. **Make Changes**
- Write code following style guidelines
- Add/update tests
- Update documentation if needed

3. **Pre-submission Checks**
```bash
# Run all checks
make test  # or equivalent

# Alternatively, run individually:
mypy cortex_service/app --strict
ruff check cortex_service/
black cortex_service/ --check
pytest cortex_service/tests/ --cov=cortex_service/app
```

4. **Commit Messages**

Use conventional commits format:

```
feat: add regime transition metrics
fix: handle None std in zscore computation
docs: update API examples in README
test: add property tests for valence clipping
refactor: extract signal rescaling to separate function
```

5. **Push and Create PR**
```bash
git push origin feature/your-feature-name
```

Create a pull request with:
- Clear description of changes
- Reference to any issues addressed
- Test coverage information
- Breaking changes (if any)

## CI/CD

### GitHub Actions (Planned)

All pull requests will run:

1. **Lint Check**
   - `ruff check`
   - `black --check`
   - `mypy --strict`

2. **Tests**
   - `pytest` with coverage report
   - Coverage threshold: >=95%

3. **Security Scan**
   - `safety` or `pip-audit` for dependency vulnerabilities

### Pre-commit Hooks (Planned)

Local checks before commit:
- Black formatting
- Ruff linting
- Type checking (mypy)

## Architecture Decisions

### When to Add a New Service

Create a new service class when:
- Business logic is complex enough to warrant separation
- Multiple endpoints share similar logic
- You need to manage state (like caching)

### When to Add a New Domain Module

Create a new domain module when:
- Adding a new category of algorithms (e.g., correlation analysis)
- The domain model has >3 related functions
- You want to keep concerns separated

### When to Add Middleware

Add middleware for:
- Cross-cutting concerns (logging, tracing, rate limiting)
- Request/response transformation
- Authentication/authorization

**Don't** add middleware for business logic.

## Performance Guidelines

1. **Signal Computation**: Keep O(n) complexity
2. **Database Queries**: Use bulk operations when safe
3. **Caching**: Consider TTL caching for frequently accessed data
4. **Metrics**: Record at boundaries, not in hot loops

## Security Guidelines

1. **Input Validation**: Always validate at API boundary with Pydantic
2. **SQL Injection**: Use SQLAlchemy ORM, never raw SQL
3. **Secrets**: Never commit secrets; use environment variables
4. **Logging**: Sanitize sensitive data before logging
5. **Dependencies**: Keep dependencies updated; check for CVEs

## Documentation

### What to Document

1. **Code**:
   - All public APIs (functions, classes, methods)
   - Complex algorithms
   - Non-obvious design decisions

2. **README**:
   - When adding new endpoints
   - When adding new configuration keys
   - When changing API contracts

3. **ARCHITECTURE.md**:
   - When adding new layers or patterns
   - When making significant architectural changes

4. **CONTRIBUTING.md** (this file):
   - When adding new development tools
   - When changing development workflow

### Updating Documentation

```bash
# After making changes
git add cortex_service/README.md
git add cortex_service/ARCHITECTURE.md
git commit -m "docs: update signal computation examples"
```

## Debugging

### Local Development

```bash
# Run with detailed logging
export CORTEX__SERVICE__LOG_LEVEL=DEBUG
uvicorn cortex_service.app.api:create_app --factory --reload --log-level debug

# Test specific endpoint
curl -X POST http://localhost:8000/signals \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: test-123" \
  -d @test_payload.json
```

### Troubleshooting

**Tests failing with database errors:**
- Check database URL in environment
- Ensure test uses in-memory SQLite
- Clear any stale test databases

**Type checking errors:**
- Run `mypy cortex_service/app --strict --show-error-codes`
- Check for missing type stubs: `pip install types-*`

**Coverage not improving:**
- Check `htmlcov/index.html` for detailed report
- Focus on untested branches
- Consider if code is testable (may need refactor)

## Getting Help

- **Issues**: File a GitHub issue with [Bug], [Feature], or [Question] prefix
- **Discussions**: Use GitHub Discussions for design questions
- **Code Review**: Tag maintainers in PR for review

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions.

## License

By contributing, you agree that your contributions will be licensed under the project's license.
