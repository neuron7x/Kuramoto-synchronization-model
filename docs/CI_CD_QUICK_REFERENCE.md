# 🚀 CI/CD Quick Reference Guide

**For Developers Working on TradePulse**

## 📋 TL;DR - What You Need to Know

Your PR must pass **5 mandatory quality gates** before it can be merged:

1. ✅ **Formatting & Linting** - ruff, black, isort, mypy
2. ✅ **Security** - No hardcoded secrets or vulnerabilities
3. ✅ **Coverage** - Maintain 98% coverage
4. ✅ **Dependencies** - No vulnerable dependencies
5. ✅ **Breaking Changes** - Document if changing public APIs

**Merge is BLOCKED until ALL gates pass.**

## ⚡ Quick Fixes

### Failed Gate 1: Formatting & Linting

```bash
# Fix all formatting issues
ruff check . --fix
black .
isort .
mypy core/ backtest/ execution/

# Verify locally before pushing
ruff check .
black --check .
isort --check-only .
```

### Failed Gate 2: Security

```bash
# Check for security issues
bandit -r core/ backtest/ execution/ application/ -ll

# Scan for secrets
pip install detect-secrets
detect-secrets scan core/ backtest/ execution/ application/

# Never commit:
# - API keys
# - Passwords
# - Private keys
# - Tokens
```

### Failed Gate 3: Coverage

```bash
# Run tests with coverage locally
pytest tests/ \
  --cov=core \
  --cov=backtest \
  --cov=execution \
  --cov-report=term-missing

# Must be ≥98%
# Add tests for any uncovered lines
```

### Failed Gate 4: Dependencies

```bash
# Check for vulnerable dependencies
pip install pip-audit
pip-audit

# Update vulnerable packages
pip install --upgrade <package-name>

# Update requirements
pip freeze > requirements.lock
```

### Failed Gate 5: Breaking Changes

If you're changing public APIs:

1. Add label `breaking-change` to PR
2. Create migration guide in `docs/`
3. Document changes in PR description

## 📊 Understanding Workflow Statuses

### Regression Validation
- **What it does:** Tests critical paths (execution, market feed, backtest, risk, orders)
- **Time:** ~30 minutes
- **When it runs:** Every PR to main/develop
- **Failing?** Check which critical path failed and review those tests

### PR Quality Gate
- **What it does:** Enforces all 5 mandatory quality checks
- **Time:** ~15 minutes
- **When it runs:** Every PR
- **Failing?** See "Quick Fixes" above

### Coverage Analysis (Weekly)
- **What it does:** Identifies coverage gaps and recommends tests to add
- **Time:** ~60 minutes
- **When it runs:** Sundays + on-demand
- **Output:** GitHub issue with top 20 test recommendations

### SBOM Enhanced (Daily)
- **What it does:** Generates Software Bill of Materials and scans for vulnerabilities
- **Time:** ~30 minutes
- **When it runs:** Daily at 02:00 UTC
- **Output:** Vulnerability reports, auto-creates issues for critical CVEs

### CI Health Monitoring (Daily)
- **What it does:** Monitors CI/CD pipeline health
- **Time:** ~15 minutes
- **When it runs:** Daily at 06:00 UTC
- **Output:** Dashboard issue updated daily

## 🔧 Local Development Workflow

### Before Creating a PR

```bash
# 1. Run formatters
black .
isort .
ruff check . --fix

# 2. Run type checking
mypy core/ backtest/ execution/

# 3. Run tests with coverage
pytest tests/ \
  --cov=core \
  --cov=backtest \
  --cov=execution \
  --cov-report=term-missing

# 4. Run security scan
bandit -r core/ backtest/ execution/ -ll

# 5. Check for secrets
detect-secrets scan core/ backtest/ execution/
```

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Coverage
- [ ] Coverage maintained at ≥98%
- [ ] New code is fully tested

## Security
- [ ] No secrets in code
- [ ] Security scan passed
- [ ] Dependencies updated

## Breaking Changes
If yes:
- [ ] Added `breaking-change` label
- [ ] Created migration guide
- [ ] Updated documentation
```

## 🚨 Emergency: PR Blocked by Quality Gate

### Step 1: Identify the Issue
Check the PR checks section to see which gate failed.

### Step 2: Fix Locally
Use the "Quick Fixes" section above for your specific gate.

### Step 3: Test Locally
```bash
# Run the same checks that CI runs
./scripts/run-quality-checks.sh  # If available

# Or manually:
ruff check .
black --check .
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-fail-under=98
bandit -r core/ backtest/ execution/ -ll
```

### Step 4: Push Fix
```bash
git add .
git commit -m "fix: Address quality gate issues"
git push
```

### Step 5: Wait for CI
CI will re-run automatically. Should complete in ~15-30 minutes.

## 🔄 What If Tests Are Flaky?

If you see intermittent test failures:

1. **Isolate the issue:** Run the test multiple times locally
   ```bash
   pytest tests/path/to/test.py::test_name -v --count=10
   ```

2. **Check for:**
   - Race conditions
   - Improper test isolation
   - External dependencies
   - Time-dependent logic

3. **Report it:** Create an issue with label `flaky-test`

4. **Don't skip it:** Fix the root cause

## 📈 Coverage Tips

### Good Coverage Practices

✅ **DO:**
- Test all code paths (if/else branches)
- Test error handling
- Test edge cases
- Test integration points

❌ **DON'T:**
- Skip tests to pass coverage
- Test only happy paths
- Ignore error cases

### Finding Uncovered Code

```bash
# Generate coverage report
pytest tests/ --cov=core --cov-report=html

# Open in browser
open htmlcov/index.html

# Look for red (uncovered) lines
```

## 🔐 Security Best Practices

### Never Commit:
- ❌ API keys
- ❌ Passwords
- ❌ Private keys
- ❌ Access tokens
- ❌ Database credentials

### Use Instead:
- ✅ Environment variables
- ✅ Secret management systems
- ✅ Configuration files (in .gitignore)

### Example:
```python
# ❌ BAD
api_key = "sk_live_abc123xyz"

# ✅ GOOD
import os
api_key = os.getenv("API_KEY")
```

## 📚 Additional Resources

### Documentation
- [Rollback Procedures](operations/ROLLBACK_PROCEDURES.md)
- [ADR-0004: CI/CD Enhancements](adr/0004-comprehensive-ci-regression-gates.md)
- [Testing Guide](../TESTING.md)

### Workflows
- [Regression Validation](../.github/workflows/regression-validation.yml)
- [PR Quality Gates](../.github/workflows/pr-quality-gate-strict.yml)
- [Coverage Analysis](../.github/workflows/coverage-analysis-deep.yml)

### Tools
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Black Documentation](https://black.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)
- [Bandit Documentation](https://bandit.readthedocs.io/)

## ❓ FAQ

### Q: My PR is blocked. Can I bypass the checks?
**A:** No. All quality gates are mandatory. Fix the issues instead.

### Q: The checks are taking too long. Can I speed them up?
**A:** Checks run in parallel where possible. Total time is ~30-45 minutes.

### Q: I only changed documentation. Do I still need 98% coverage?
**A:** Coverage checks only run on code changes. Documentation-only PRs are not affected.

### Q: What if I disagree with a linting rule?
**A:** Open an issue to discuss changing the rule. Don't skip it in your code.

### Q: My tests pass locally but fail in CI. Why?
**A:** Common causes:
- Different Python version
- Missing dependencies
- Environment-specific issues
- Race conditions

Check the CI logs for details.

### Q: How do I add a new dependency?
**A:** 
1. Add to `requirements.txt`
2. Run `pip-audit` to check for vulnerabilities
3. Update `requirements.lock`
4. Document why it's needed in PR description

### Q: What if I need to make a breaking change?
**A:**
1. Add `breaking-change` label to PR
2. Create migration guide in `docs/`
3. Update API documentation
4. Notify team leads
5. Plan rollout strategy

## 🆘 Getting Help

### Workflow Issues
- Check GitHub Actions logs
- Look for error messages
- Review recent changes to workflows

### Test Failures
- Run locally first
- Check test isolation
- Look for flaky tests
- Review test logs

### Quality Gate Questions
- Consult this guide
- Ask in team chat
- Create a discussion issue

### Emergency Rollback
- Follow [Rollback Procedures](operations/ROLLBACK_PROCEDURES.md)
- Alert on-call engineer
- Document incident

---

**Last Updated:** 2025-11-18  
**Maintained By:** Principal System Architect  
**Questions?** Create an issue with label `ci-cd-question`
