# Python Version Policy

## Single Source of Truth

**`pyproject.toml`** is the canonical source for supported Python versions via the `requires-python` field.

Current constraint: `requires-python = ">=3.11,<3.13"`  
**Supported versions: Python 3.11, 3.12**

## Alignment Enforcement

All Python version declarations across the repository **must** align with `pyproject.toml`:

- **Dockerfiles**: All `FROM python:X.Y` statements
- **GitHub Actions**: All `python-version` fields in workflows
- **Development tools**: `.python-version`, `.pre-commit-config.yaml`
- **Documentation**: README.md, setup guides

## Automated Drift Prevention

### Local Verification

```bash
make guard-python-matrix
```

This runs `scripts/check_python_matrix.py` which:
- Parses `requires-python` from `pyproject.toml`
- Scans all Dockerfiles for `FROM python:X.Y`
- Scans all GitHub Actions workflows for `python-version` declarations
- Validates `.python-version` file
- **Exits with code 1** if any drift is detected

### CI Enforcement

The `python-matrix-guard` job in `.github/workflows/tests.yml` runs on every PR and blocks merge if version drift is detected.

## Updating Python Version Range

To update the supported Python version range:

1. **Update `pyproject.toml`**:
   ```toml
   requires-python = ">=3.X,<3.Y"
   ```

2. **Update classifiers** in the same file:
   ```toml
   "Programming Language :: Python :: 3.X",
   "Programming Language :: Python :: 3.Y",
   ```

3. **Run verification**:
   ```bash
   make guard-python-matrix
   ```

4. **Fix any reported drift** in Dockerfiles or CI workflows

5. **Update `.python-version`** to the recommended development version (typically the latest supported minor)

6. **Test thoroughly**:
   - Run full test suite across all supported versions
   - Verify dependency compatibility
   - Build and test Docker images

## Files Under Automatic Verification

- `Dockerfile` (all stages)
- `sandbox/Dockerfile`
- `cortex_service/Dockerfile`
- `.github/workflows/*.yml` (all workflow files)
- `.python-version`

## Rationale

**Why enforce strict alignment?**

1. **Prevents accidental breakage**: Building with unsupported Python versions in CI/Docker can hide compatibility issues
2. **Clear compatibility promise**: Users know exactly which Python versions are tested and supported
3. **Easier maintenance**: Single source of truth reduces maintenance burden
4. **CI reliability**: Consistent versions across matrix tests ensure reproducible builds

**Why `pyproject.toml` as source of truth?**

- Standard Python packaging metadata (PEP 621)
- Used by pip, build tools, and package indexes
- Checked by dependency resolvers
- Natural place for project-wide Python constraints

## History

- **2025-12-13**: Implemented deterministic version matrix alignment with automated drift detection
