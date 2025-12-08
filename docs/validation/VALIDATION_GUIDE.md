# Repository Validation Guide

## Overview

The TradePulse repository validation infrastructure provides comprehensive, automated validation across 10 categories to ensure code quality, security, and integrity.

## Features

### Core Capabilities

1. **Weighted Health Scoring** (0-100)
   - Security: 25% (highest priority)
   - Test Suite: 20%
   - Module Imports: 15%
   - Code Integrity: 15%
   - Configuration: 10%
   - Build System: 5%
   - Data Integrity: 5%
   - Documentation: 3%
   - File Integrity: 2%
   - Git Repository: 0% (informational)

2. **Intelligent Classification**
   - Environment issues → WARNING (doesn't block pipeline)
   - Code problems → ERROR (blocks pipeline)
   - Security vulnerabilities → CRITICAL (blocks and caps score at 60)

3. **Security Hardening**
   - Actions pinned by SHA (not tags)
   - Minimal permissions (principle of least privilege)
   - Dependencies pinned with versions
   - No hardcoded secrets

4. **Performance Optimizations**
   - Parallel execution (5x faster)
   - Result caching (skip unchanged files)
   - Progress indicators with ETA
   - Automatic report cleanup (30-day retention)

## Usage

### Basic Usage

```bash
# Run validation with default settings
python scripts/comprehensive_repository_validation.py

# Verbose output
python scripts/comprehensive_repository_validation.py --verbose

# Custom output locations
python scripts/comprehensive_repository_validation.py \
    --output reports/custom_report.md \
    --json-output reports/custom_report.json
```

### CI/CD Integration

The validation runs automatically in GitHub Actions on:
- Push to main, develop, copilot/** branches
- Pull requests to main, develop
- Manual workflow dispatch
- Daily schedule (6 AM UTC)

### Exit Codes

- **0**: No critical or error failures (warnings OK)
- **1**: Has critical or error failures (blocks deployment)

## Validation Categories

### 1. Code Integrity

**Checks:**
- Python syntax validation (AST compilation)
- All 1,755 Python files validated

**Severity:**
- Syntax errors: ERROR (blocks pipeline)

### 2. Configuration

**Checks:**
- YAML validation (43 files)
- JSON validation (2 files)
- TOML validation (2 files)

**Files validated:**
- Neuromodulator configs (dopamine, serotonin, GABA)
- Risk engine configs
- Market adapter configs
- Application configs

**Severity:**
- Invalid configs: ERROR (blocks pipeline)

### 3. Module Imports

**Checks:**
- Core module imports
- Dependency availability detection
- ModuleNotFoundError parsing

**Classification:**
- Missing dependencies → WARNING (environment issue)
- Non-existent modules → INFO (expected)
- Import errors → ERROR (code issue)

### 4. Security Scanning

**Checks:**
- pip-audit vulnerability scanning
- Hardcoded secrets detection
- Dependency version checking

**Severity levels:**
- Critical vulnerabilities (RCE) → CRITICAL
- High-risk vulnerabilities → ERROR
- Medium/Low vulnerabilities → WARNING

**Output:**
- Structured JSON with CVE details
- Severity categorization (CRITICAL/HIGH/MEDIUM/LOW)
- Actionable recommendations

### 5. Test Suite

**Checks:**
- pytest availability
- Test discovery
- Optional dependency detection

**Classification:**
- pytest not installed → WARNING (environment)
- Missing optional deps → WARNING (environment)
- Real test failures → ERROR (code issue)

### 6. Build System

**Checks:**
- Makefile existence
- pyproject.toml validation
- Tool availability (ruff, mypy)

**Severity:**
- Invalid pyproject.toml → ERROR
- Missing tools → WARNING (environment)

### 7. Data Integrity

**Checks:**
- CSV validation (OHLCV data)
- File checksums (SHA-256)
- Data schema validation

**Severity:**
- Missing pandas → WARNING (environment)
- Invalid data → ERROR (code issue)

### 8. Documentation

**Checks:**
- README existence and validity
- Documentation structure
- Markdown syntax

**Severity:**
- Missing docs → WARNING
- Invalid structure → ERROR

### 9. File Integrity

**Checks:**
- SHA-256 checksums
- File existence
- File access permissions

**Severity:**
- Checksum failures → WARNING (environment)

### 10. Git Repository

**Checks:**
- .git directory existence
- Git status
- Commit/branch information

**Severity:**
- Not a git repo → CRITICAL
- Git access issues → WARNING (environment)

## Health Score Interpretation

| Score | Rating | Status |
|-------|--------|--------|
| 90-100 | Excellent ⭐⭐⭐⭐⭐ | Production ready |
| 70-89 | Good ⭐⭐⭐⭐ | Minor issues |
| 50-69 | Fair ⭐⭐⭐ | Needs attention |
| 30-49 | Poor ⭐⭐ | Significant issues |
| 0-29 | Critical ⭐ | Not deployable |

## Known Issues & Troubleshooting

### Common Warnings

**Missing Dependencies:**
```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

**Missing Dev Tools:**
```bash
# Install pytest
pip install pytest pytest-asyncio pytest-cov

# Install type checker
pip install mypy

# Install linter
pip install ruff

# Install security scanner
pip install pip-audit
```

**pandas for Data Validation:**
```bash
pip install pandas
```

### Environment vs Code Issues

**Environment Issues (WARNING):**
- Missing optional dependencies
- Tool not installed
- pandas not available for CSV validation
- pip-audit not available locally

**Code Issues (ERROR):**
- Python syntax errors
- Invalid YAML/JSON/TOML configs
- Invalid pyproject.toml
- Real module import errors

## Performance Tips

### Faster Validation

1. **Use caching**: Results are cached for unchanged files
2. **Skip optional checks**: Use environment variables to skip non-critical checks
3. **Parallel execution**: Enabled by default (5x faster)

### CI/CD Optimization

1. **Cache pip dependencies**: Already enabled in workflow
2. **Artifact retention**: 30 days (configurable)
3. **Conditional execution**: Only on relevant file changes

## Advanced Configuration

### Environment Variables

```bash
# Skip data validation
export SKIP_DATA_VALIDATION=true

# Skip security scans
export SKIP_SECURITY_SCANS=true

# Increase timeout
export VALIDATION_TIMEOUT=300

# Disable caching
export DISABLE_VALIDATION_CACHE=true
```

### Custom Weights

Edit `scripts/comprehensive_repository_validation.py`:

```python
CATEGORY_WEIGHTS = {
    "Security": 0.30,  # Increase security weight
    "Test Suite": 0.25,  # Increase test weight
    # ... other categories
}
```

## Report Formats

### Markdown Report

- Executive summary
- Health score breakdown
- Known issues section
- Detailed results by category
- Actionable recommendations

### JSON Report

- Structured data for programmatic consumption
- All check results with details
- Category breakdown
- overall_status field
- Timestamp and metadata

## Integration Examples

### GitHub Actions

```yaml
- name: Run validation
  run: |
    python scripts/comprehensive_repository_validation.py \
      --output reports/validation.md \
      --json-output reports/validation.json

- name: Upload reports
  uses: actions/upload-artifact@v4
  with:
    name: validation-reports
    path: reports/
    retention-days: 30
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

python scripts/comprehensive_repository_validation.py --verbose
if [ $? -ne 0 ]; then
    echo "Validation failed! Please fix errors before committing."
    exit 1
fi
```

### CI/CD Pipeline

```yaml
# .gitlab-ci.yml
validation:
  script:
    - python scripts/comprehensive_repository_validation.py
  artifacts:
    reports:
      junit: reports/validation.json
    paths:
      - reports/
    expire_in: 30 days
```

## FAQ

### Q: Why is my health score low?

A: Check the category breakdown in the report. Focus on high-weight categories (Security, Tests, Module Imports) first.

### Q: How do I fix missing dependency warnings?

A: Install dependencies with `pip install -r requirements.txt requirements-dev.txt`. These are environment issues and don't block deployment.

### Q: What causes exit code 1?

A: Only CRITICAL or ERROR severity failures cause exit code 1. These are real code problems (syntax errors, invalid configs) that must be fixed.

### Q: Can I run validation locally?

A: Yes! Just run `python scripts/comprehensive_repository_validation.py`. Install dependencies first for full validation.

### Q: How do I add custom checks?

A: Edit `scripts/comprehensive_repository_validation.py` and add new validation methods. Follow the existing pattern and use appropriate severity levels.

## Support

For issues or questions:
1. Check this guide
2. Review the report's "Known Issues" section
3. Check GitHub Actions logs
4. Review docs/validation/HEALTH_SCORE.md for scoring details

## References

- [Health Score Methodology](./HEALTH_SCORE.md)
- [GitHub Actions Workflow](../../.github/workflows/comprehensive_repository_validation.yml)
- [Validation Script](../../scripts/comprehensive_repository_validation.py)
