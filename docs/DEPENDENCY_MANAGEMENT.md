# Dependency Management Guide

This document explains how TradePulse manages Python dependencies to ensure reproducible builds, security, and maintainability.

## Overview

TradePulse uses a **multi-layered dependency management approach**:

1. **Abstract dependencies** in `pyproject.toml` (source of truth)
2. **Concrete lock files** (`requirements.lock`, `requirements-dev.lock`)
3. **Security constraints** in `constraints/security.txt`

## File Structure

```
TradePulse/
├── pyproject.toml              # Source of truth for dependencies
├── requirements.txt            # Runtime dependencies (abstract)
├── requirements-dev.txt        # Dev dependencies (abstract)
├── requirements.lock           # Pinned runtime dependencies
├── requirements-dev.lock       # Pinned dev dependencies
└── constraints/
    └── security.txt            # Security-critical pins
```

### File Descriptions

| File | Purpose | Committed | Generated |
|------|---------|-----------|-----------|
| `pyproject.toml` | Source of truth, defines abstract deps with ranges | ✅ Yes | ❌ No |
| `requirements.txt` | Runtime dependencies derived from pyproject.toml | ✅ Yes | ❌ No |
| `requirements-dev.txt` | Dev dependencies derived from pyproject.toml | ✅ Yes | ❌ No |
| `requirements.lock` | Exact runtime dependency versions | ✅ Yes | ✅ Yes |
| `requirements-dev.lock` | Exact dev dependency versions | ✅ Yes | ✅ Yes |
| `constraints/security.txt` | Security pins for critical packages | ✅ Yes | ❌ No |

## Installation

### For End Users

```bash
# Runtime dependencies only
make install

# Or manually:
pip install -c constraints/security.txt -r requirements.lock
```

### For Developers

```bash
# Full development environment
make dev-install

# Or manually:
pip install -c constraints/security.txt -r requirements.lock
pip install -c constraints/security.txt -r requirements-dev.lock
```

## Adding Dependencies

### 1. Add to pyproject.toml

Edit `pyproject.toml` and add your dependency in the appropriate section:

```toml
[project]
dependencies = [
    "requests>=2.32.0,<3.0.0",     # Runtime dependency
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",                # Dev/test tool
]
```

### 2. Update requirements files

Manually sync the dependency to `requirements.txt` or `requirements-dev.txt`:

```bash
# Add to requirements.txt for runtime deps
echo "requests>=2.32.0,<3.0.0" >> requirements.txt

# Or add to requirements-dev.txt for dev deps
echo "pytest>=8.0.0" >> requirements-dev.txt
```

### 3. Regenerate lock files

```bash
make deps-update
```

This runs:
```bash
pip-compile --constraint=constraints/security.txt \
    --no-annotate \
    --output-file=requirements.lock \
    --strip-extras requirements.txt

pip-compile --constraint=constraints/security.txt \
    --no-annotate \
    --output-file=requirements-dev.lock \
    --strip-extras requirements-dev.txt
```

### 4. Run security audit

```bash
make deps-audit
```

Address any HIGH or CRITICAL vulnerabilities found.

### 5. Test the changes

```bash
# Install updated dependencies
make dev-install

# Run tests
make test

# Run linters
make lint
```

### 6. Commit all changes

```bash
git add pyproject.toml requirements*.txt requirements*.lock
git commit -m "Add <package-name> dependency"
```

## Updating Dependencies

To update all dependencies to their latest compatible versions:

```bash
# Regenerate lock files
make deps-update

# Audit for vulnerabilities
make deps-audit

# Test thoroughly
make test-all

# If all passes, commit
git add requirements*.lock
git commit -m "Update dependencies"
```

## Security Management

### Security Constraints File

`constraints/security.txt` pins security-critical packages to safe versions:

```txt
# Example entries
urllib3==2.6.0              # CVE-2025-66418, CVE-2025-66471
starlette>=0.50.0           # CVE-2025-52316
cryptography==46.0.3        # Multiple CVEs in older versions
```

### Security Audit Workflow

1. **Run audit regularly:**
   ```bash
   make deps-audit
   ```

2. **Review findings:**
   - HIGH/CRITICAL: Fix immediately (within 7 days)
   - MEDIUM: Fix in next release
   - LOW: Fix when convenient

3. **Update vulnerable packages:**
   ```bash
   # Update pyproject.toml with new version constraints
   # Then regenerate lock files
   make deps-update
   ```

4. **Add to security constraints if needed:**
   ```bash
   # Edit constraints/security.txt to pin the fixed version
   echo "package-name==X.Y.Z  # CVE-YYYY-XXXXX" >> constraints/security.txt
   ```

5. **Verify fix:**
   ```bash
   make deps-audit  # Should show no issues for that package
   ```

## Troubleshooting

### Lock file generation fails

**Error: "ResolutionImpossible" or dependency conflicts**

1. Check version constraints in `pyproject.toml` for conflicts
2. Review `constraints/security.txt` for overly restrictive pins
3. Try updating one dependency at a time
4. Use `pip-compile --verbose` for detailed output

### Installation fails

**Error: "Could not find a version that satisfies the requirement"**

1. Verify Python version matches requirements (3.11-3.12)
2. Check if using correct constraints file
3. Ensure pip is up-to-date: `pip install --upgrade pip`

### Security audit shows false positives

1. Verify the vulnerability applies to your usage
2. Document the exception in `constraints/security.txt`
3. Consider using `pip-audit --ignore-vuln CVE-YYYY-XXXXX`

## Best Practices

### ✅ DO

- Always use lock files for installations
- Run `make deps-audit` before releases
- Pin security-critical dependencies
- Test after updating dependencies
- Commit lock files to version control
- Document security exceptions

### ❌ DON'T

- Manually edit lock files
- Use `pip install` without constraints
- Ignore HIGH/CRITICAL CVEs
- Install packages outside lock files in production
- Use floating versions (>=) for security packages
- Skip testing after dependency updates

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Install dependencies
  run: |
    pip install --upgrade pip setuptools wheel
    pip install -c constraints/security.txt -r requirements-dev.lock

- name: Security audit
  run: make deps-audit
  continue-on-error: true  # Don't fail build, but show warnings
```

### Docker Example

```dockerfile
FROM python:3.11-slim

COPY requirements.lock constraints/security.txt ./
RUN pip install --no-cache-dir -c constraints/security.txt -r requirements.lock
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make install` | Install runtime dependencies |
| `make dev-install` | Install dev dependencies |
| `make deps-update` | Regenerate lock files |
| `make deps-audit` | Security audit |
| `make clean-deps` | Clean dependency caches |

## References

- [pip-tools Documentation](https://pip-tools.readthedocs.io/)
- [pip-audit Documentation](https://pypi.org/project/pip-audit/)
- [Python Packaging Guide](https://packaging.python.org/)
- [Security Best Practices](https://www.python.org/dev/security/)
