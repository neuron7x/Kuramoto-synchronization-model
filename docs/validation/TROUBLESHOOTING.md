# Validation Troubleshooting Guide

## Common Issues and Solutions

### Exit Code 1: Validation Failed

#### Cause

The validation script returns exit code 1 when there are CRITICAL or ERROR severity failures.

#### Solution

1. Check the validation report:
```bash
cat reports/REPOSITORY_VALIDATION_REPORT.md
```

2. Look for ERROR or CRITICAL failures (not warnings)

3. Common ERROR causes:
   - Python syntax errors → Fix the syntax in the reported files
   - Invalid YAML/JSON/TOML configs → Validate and fix configuration files
   - Invalid pyproject.toml → Check project metadata

#### Example Fix

```bash
# Python syntax error
Error: invalid syntax in src/module.py line 42

Fix: Open the file and correct the syntax error
```

### Missing Dependencies (WARNING)

#### Cause

Modules like numpy, pydantic are not installed in the validation environment.

#### Solution

These are **WARNING** level (not errors) and don't block the pipeline. To fix locally:

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies  
pip install -r requirements-dev.txt

# Or install specific missing dependency
pip install numpy pydantic pandas
```

#### Why This Happens

- Validation runs in a minimal environment by design
- Missing dependencies are expected without full install
- CI installs dependencies before running validation

### pytest Not Available (WARNING)

#### Cause

pytest is not installed in the validation environment.

#### Solution

```bash
# Install pytest and plugins
pip install pytest pytest-asyncio pytest-cov pytest-xdist

# Or install all dev dependencies
pip install -r requirements-dev.txt
```

#### Note

This is a WARNING (not an error) and doesn't block the pipeline. The validation continues without running test discovery.

### pip-audit Failed (WARNING)

#### Cause

pip-audit tool is not installed locally.

#### Solution

```bash
# Install pip-audit
pip install pip-audit

# Run security scan manually
pip-audit --format=json
```

#### Note

- This is WARNING level (doesn't block)
- pip-audit is typically run in CI, not locally
- Expected to be missing in development environments

### pandas Module Not Found (WARNING)

#### Cause

pandas is not installed, so CSV data validation is skipped.

#### Solution

```bash
# Install pandas
pip install pandas

# Or install all dependencies
pip install -r requirements.txt
```

#### Note

- WARNING level (doesn't block)
- Data validation is optional
- CSV files are still validated for existence

### mypy/ruff Not Available (WARNING)

#### Cause

Development tools are not installed.

#### Solution

```bash
# Install type checker
pip install mypy

# Install linter
pip install ruff

# Or install all dev tools
pip install -r requirements-dev.txt
```

#### Impact

- WARNING level only
- Doesn't block pipeline
- These checks are optional for local development

### Git Status Failed (WARNING)

#### Cause

Git command failed or repository access issues.

#### Solution

1. Check if you're in a git repository:
```bash
git status
```

2. Check git configuration:
```bash
git config --list
```

3. Verify repository integrity:
```bash
git fsck
```

#### Note

- WARNING level (environment issue)
- Doesn't block validation
- Common in containerized environments

### Checksum Failures (WARNING)

#### Cause

File checksum calculation failed due to file access issues.

#### Solution

1. Check file permissions:
```bash
ls -la <file_path>
```

2. Verify file exists:
```bash
test -f <file_path> && echo "exists" || echo "missing"
```

3. Check disk space:
```bash
df -h
```

#### Note

- WARNING level (environment/filesystem issue)
- Doesn't block validation
- Files are still validated for existence

### Invalid Configuration (ERROR)

#### Cause

YAML, JSON, or TOML file has syntax errors.

#### Solution

1. Identify the invalid file from the report
2. Validate the file:

```bash
# For YAML
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# For JSON
python -c "import json; json.load(open('config.json'))"

# For TOML
python -c "import tomli; tomli.load(open('pyproject.toml', 'rb'))"
```

3. Fix syntax errors using a validator:
   - YAML: https://yaml-lint.com/
   - JSON: https://jsonlint.com/
   - TOML: https://www.toml-lint.com/

#### Example

```yaml
# INVALID (ERROR)
key: value
  indented_wrong: value  # Incorrect indentation

# VALID
key: value
indented_correct: value  # Correct indentation
```

### Module Import Errors (ERROR vs WARNING)

#### ERROR (blocks pipeline)

Real code issues where the module exists but has import errors:

```python
# Example: ImportError due to circular dependency
from module_a import ClassA  # Fails with ImportError
```

**Solution**: Fix the code issue (circular dependency, missing __init__.py, etc.)

#### WARNING (doesn't block)

Environment issues where dependencies are missing:

```python
# Example: ModuleNotFoundError for numpy
import numpy  # Missing dependency
```

**Solution**: Install the dependency (`pip install numpy`)

### Health Score Too Low

#### Cause

Weighted scoring heavily penalizes failures in high-priority categories (Security 25%, Tests 20%, Module Imports 15%).

#### Solution

1. Check category breakdown in the report
2. Focus on high-weight categories first:

**Priority Order:**
1. Security (25% weight)
   - Fix security findings
   - Update vulnerable dependencies
   - Remove hardcoded secrets

2. Test Suite (20% weight)
   - Install pytest
   - Fix test collection failures
   - Ensure tests run successfully

3. Module Imports (15% weight)
   - Install missing dependencies
   - Fix import errors
   - Resolve circular dependencies

4. Code Integrity (15% weight)
   - Fix syntax errors
   - Ensure all Python files are valid

#### Example

```
Current: 37/100 ⭐⭐
Goal: 70+/100 ⭐⭐⭐⭐

Action Plan:
1. Fix Security findings → +15 points
2. Install pytest → +10 points
3. Install numpy, pydantic → +8 points
4. Total: 70/100 ⭐⭐⭐⭐
```

### CI Pipeline Failed

#### Cause

Validation job failed with exit code 1.

#### Solution

1. Check GitHub Actions logs:
```
Actions → Repository Validation → View logs
```

2. Download artifacts:
```
Actions → Repository Validation → Artifacts → validation-reports
```

3. Review the report for ERROR or CRITICAL failures

4. Fix issues and push changes

#### Common CI Issues

**Cache Restore Failed (400):**
- This is a WARNING from actions/cache
- Doesn't affect validation
- Safe to ignore

**Dependencies Not Installed:**
- Check workflow installs requirements.txt
- Verify workflow installs requirements-dev.txt
- Check for typos in dependency names

**Permissions Issues:**
- Verify workflow has correct permissions
- Check actions are pinned by SHA
- Ensure GITHUB_TOKEN has necessary scopes

### Performance Issues

#### Slow Validation (>2 minutes)

**Cause**: Sequential execution or large repository.

**Solution**:

1. Verify parallel execution is enabled (should be default)
2. Check for timeout issues in logs
3. Skip optional checks:

```bash
export SKIP_DATA_VALIDATION=true
python scripts/comprehensive_repository_validation.py
```

#### High Memory Usage

**Cause**: Large files or many parallel checks.

**Solution**:

1. Reduce parallelism:
```python
# Edit script: reduce max_workers
max_workers = 2  # Default is 5
```

2. Skip memory-intensive checks:
```bash
export SKIP_SYNTAX_VALIDATION=true
```

### Report Generation Failed

#### Cause

File permissions or disk space issues.

#### Solution

1. Check disk space:
```bash
df -h reports/
```

2. Check permissions:
```bash
ls -la reports/
chmod 755 reports/
```

3. Create reports directory:
```bash
mkdir -p reports
```

### Caching Issues

#### Stale Cache Results

**Cause**: Cache not invalidated after file changes.

**Solution**:

```bash
# Disable cache for one run
export DISABLE_VALIDATION_CACHE=true
python scripts/comprehensive_repository_validation.py

# Or clear cache
rm -rf .validation_cache/
```

## Debugging Tips

### Enable Verbose Mode

```bash
python scripts/comprehensive_repository_validation.py --verbose
```

### Check JSON Output

```bash
# Pretty-print JSON report
python -m json.tool reports/repository_validation.json

# Extract failed checks
jq '.checks[] | select(.passed == false)' reports/repository_validation.json
```

### Review Detailed Logs

```bash
# Check validation log (if logging enabled)
cat validation.log

# Filter for errors
grep ERROR validation.log
```

### Test Individual Categories

```python
# Edit script to test one category
validator = RepositoryValidator(Path.cwd())
validator.validate_git_repository()  # Test only git validation
```

## Prevention

### Pre-commit Hooks

```bash
# Install pre-commit hook
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
python scripts/comprehensive_repository_validation.py --verbose
if [ $? -ne 0 ]; then
    echo "Validation failed! Fix errors before committing."
    exit 1
fi
EOF

chmod +x .git/hooks/pre-commit
```

### Local Testing Before Push

```bash
# Run full validation locally
pip install -r requirements.txt requirements-dev.txt
python scripts/comprehensive_repository_validation.py

# Check exit code
echo $?  # Should be 0
```

### Regular Maintenance

1. **Weekly**: Review validation reports
2. **Monthly**: Update dependencies
3. **Quarterly**: Review and update validation logic

## Getting Help

If you're still stuck:

1. **Check documentation**:
   - [Validation Guide](./VALIDATION_GUIDE.md)
   - [Health Score Methodology](./HEALTH_SCORE.md)

2. **Review recent changes**:
```bash
git log --oneline -10 scripts/comprehensive_repository_validation.py
```

3. **Check for known issues**:
```bash
# Search report for known issues section
grep -A 20 "Known Issues" reports/REPOSITORY_VALIDATION_REPORT.md
```

4. **Compare with main branch**:
```bash
git diff main scripts/comprehensive_repository_validation.py
```

## Summary Checklist

Before seeking help, verify:

- [ ] Reviewed the validation report
- [ ] Checked if issues are WARNING (not blocking) vs ERROR (blocking)
- [ ] Installed required dependencies
- [ ] Verified git repository integrity
- [ ] Checked file permissions
- [ ] Reviewed GitHub Actions logs (for CI failures)
- [ ] Tested locally with verbose mode
- [ ] Checked JSON output for details
- [ ] Reviewed known issues section in report

## Quick Reference

| Issue | Severity | Blocks Pipeline? | Solution |
|-------|----------|------------------|----------|
| Missing dependencies | WARNING | No | `pip install -r requirements.txt` |
| pytest not available | WARNING | No | `pip install pytest` |
| pip-audit failed | WARNING | No | `pip install pip-audit` (optional) |
| Python syntax error | ERROR | Yes | Fix syntax in reported file |
| Invalid YAML/JSON | ERROR | Yes | Fix configuration file syntax |
| Git status failed | WARNING | No | Check git repository access |
| Checksum failed | WARNING | No | Check file permissions |
| Import error (code) | ERROR | Yes | Fix code issue |
| Import error (deps) | WARNING | No | Install missing dependency |
