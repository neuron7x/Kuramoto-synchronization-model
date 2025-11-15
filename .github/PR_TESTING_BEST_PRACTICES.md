# PR Testing Best Practices & Security Guidelines

> **Last Updated:** 2025-11-15  
> **Version:** 1.0  
> **Status:** Active

## Table of Contents
- [Overview](#overview)
- [Security Improvements](#security-improvements)
- [Quality Gates](#quality-gates)
- [Common Issues & Solutions](#common-issues--solutions)
- [Workflow Health Monitoring](#workflow-health-monitoring)

## Overview

This document outlines the current state and best practices for PR testing in TradePulse. It addresses weaknesses identified in the testing infrastructure and provides practical solutions.

### Recent Improvements (2025-11-15)

✅ **Fixed Critical YAML Syntax Errors**
- Fixed Python heredoc indentation in 4 workflow files
- All 48 workflows now parse correctly
- Prevents workflow execution failures

✅ **Added Missing Permissions**
- Added explicit permissions to 3 workflows
- Follows principle of least privilege
- Improves security posture

✅ **Improved Mutation Testing**
- Removed `continue-on-error: true` weakness
- Proper failure handling with informative messages
- Kill rate enforcement now works correctly

✅ **Created Action Pinning Check**
- New workflow monitors unpinned actions
- Provides security warnings on PRs
- Generates detailed reports

## Security Improvements

### 1. Action Pinning (In Progress)

**Current Status:** ⚠️ 258 actions not pinned to commit SHAs

**Risk:** Tags can be moved to point to malicious code

**Solution:**
```yaml
# ❌ Bad - vulnerable to tag manipulation
uses: actions/checkout@v4

# ✅ Good - pinned to immutable commit
uses: actions/checkout@08eba0b27e82efb55e67dbb0c8ae4baf47a1b22f # v4.2.2
```

**Action Plan:**
1. New `action-pinning-check.yml` workflow monitors unpinned actions
2. Dependabot automatically updates pinned actions weekly
3. Use format: `owner/action@<40-char-sha> # vX.Y.Z` for human readability

**Most Common Actions to Pin:**
- actions/checkout (101 instances)
- actions/setup-python (60 instances)
- actions/upload-artifact (59 instances)
- actions/github-script (24 instances)
- actions/cache (11 instances)

### 2. Workflow Permissions

**Status:** ✅ Complete - All workflows now have explicit permissions

**Best Practice:**
```yaml
# Always specify minimal permissions
permissions:
  contents: read          # Read repository contents
  pull-requests: write    # Comment on PRs (if needed)
  # Never use 'write-all' or omit permissions
```

**Fixed Workflows:**
- `dopamine-validation.yml` - Added read/write permissions
- `nak-ci.yml` - Added read-only permissions
- `neural-controller-ci.yml` - Added read/write permissions

### 3. Secret Scanning

**Current Coverage:**
- ✅ Gitleaks - Git history scanning
- ✅ TruffleHog - Verified secret detection
- ✅ detect-secrets - Pre-commit hook
- ✅ Custom Python scanner for hardcoded secrets

**Recommendations:**
- Integrate GitHub Secret Scanning (if not enabled)
- Add secret rotation policies
- Use GitHub Secrets for all credentials

### 4. Dependency Scanning

**Current Coverage:**
- ✅ Python: Safety, pip-audit
- ✅ Container: Trivy, Grype
- ⚠️ JavaScript: Limited coverage
- ⚠️ Go: Limited coverage
- ⚠️ Rust: Limited coverage

**Recommendations:**
- Add npm audit for JavaScript dependencies
- Add Go vulnerability scanning (govulncheck)
- Add cargo audit for Rust dependencies

## Quality Gates

### 1. Code Coverage

**Threshold:** ≥98% line coverage, ≥90% branch coverage

**Workflow:** `ci.yml` - Test Coverage

**Status:** ✅ Properly enforced

**Best Practices:**
- Use sharded execution (3 shards) for faster feedback
- Mark test-only code with `# pragma: no cover`
- Focus on critical modules: core, backtest, execution

### 2. Mutation Testing

**Threshold:** ≥90% mutation kill rate

**Workflow:** `mutation-testing.yml`

**Recent Fix:** ✅ Removed `continue-on-error: true`

**Purpose:** Ensures tests actually catch bugs, not just coverage metrics

**Best Practices:**
- Run mutations on critical code paths
- Strengthen assertions in tests
- Add edge case tests
- Review surviving mutants manually

### 3. Security Scanning

**Workflows:**
- `security.yml` - Multi-layer security scanning
- `semgrep.yml` - Pattern-based security rules
- `dependency-review.yml` - License and vulnerability checks

**Status:** ✅ Comprehensive coverage

**Best Practices:**
- Fix critical and high vulnerabilities immediately
- Document accepted risks for medium/low issues
- Update dependencies regularly via Dependabot

### 4. Performance Regression

**Threshold:**
- Warning: >10% slowdown
- Failure: >25% slowdown
- Memory: >20% increase

**Workflow:** `performance-regression-pr.yml`

**Status:** ✅ Active

**Best Practices:**
- Benchmark critical code paths
- Use multiple runs for statistical accuracy
- Document intentional performance trade-offs

### 5. Complexity Analysis

**Thresholds:**
- Average cyclomatic complexity: <10
- Maximum cyclomatic complexity: <15
- PR size: <500 lines preferred, <1000 acceptable

**Workflow:** `pr-complexity-analysis.yml`

**Status:** ✅ Active

**Best Practices:**
- Break large PRs into smaller, focused changes
- Refactor complex functions
- Use early returns to reduce nesting

## Common Issues & Solutions

### Issue 1: YAML Syntax Errors

**Symptoms:**
- Workflow fails to start
- "could not find expected ':'" error
- Parser errors in workflow logs

**Solution:**
```yaml
# ❌ Bad - heredoc not properly indented
run: |
  python <<'EOF'
import sys
print("hello")
EOF

# ✅ Good - heredoc properly indented at same level as script
run: |
  python <<'EOF'
  import sys
  print("hello")
  EOF
```

**Prevention:**
- Use YAML linters (yamllint)
- Validate workflows before commit
- Use consistent indentation (2 spaces)

### Issue 2: Mutation Testing Failures

**Symptoms:**
- Tests pass but mutation testing fails
- Low kill rate (<90%)
- Surviving mutants

**Solution:**
1. Review surviving mutants: `mutmut results`
2. Strengthen test assertions
3. Add edge case tests
4. Test boundary conditions

**Example:**
```python
# ❌ Weak test - doesn't catch off-by-one errors
def test_range():
    result = get_range(0, 10)
    assert result  # Just checks it's not empty

# ✅ Strong test - catches mutations
def test_range():
    result = get_range(0, 10)
    assert len(result) == 10  # Checks exact length
    assert result[0] == 0     # Checks start
    assert result[-1] == 9    # Checks end
```

### Issue 3: Coverage Failures

**Symptoms:**
- Coverage below 98%
- "missing-coverage" label on PR
- Merge blocked

**Solution:**
1. Check coverage report: `coverage html`
2. Add tests for uncovered lines
3. Remove dead code
4. Mark test utilities with `# pragma: no cover`

**Common Causes:**
- Missing error path tests
- Uncovered exception handlers
- New code without tests
- Configuration code

### Issue 4: Security Scan Failures

**Symptoms:**
- Critical or high vulnerabilities detected
- Security workflow fails
- Merge blocked

**Solution:**
1. Review security findings in workflow artifacts
2. Update vulnerable dependencies
3. Apply security patches
4. Document risk acceptance if fix unavailable

**Priority:**
- Critical: Fix immediately
- High: Fix before merge
- Medium: Fix in follow-up PR
- Low: Schedule for future sprint

### Issue 5: Performance Regressions

**Symptoms:**
- Performance regression workflow warns/fails
- >10% slowdown detected
- Memory usage increased

**Solution:**
1. Profile the code: `python -m cProfile`
2. Identify hot paths
3. Optimize algorithms
4. Add caching where appropriate
5. Document intentional trade-offs

**Example:**
```python
# Document performance trade-off
# Note: This implementation prioritizes correctness over performance
# for critical financial calculations. ~15% slower but guarantees
# decimal precision required for monetary amounts.
```

## Workflow Health Monitoring

### Key Metrics

**Execution Time:**
- Coverage: ~8 minutes (sharded)
- Mutation Testing: ~15 minutes
- Security Scans: ~5 minutes
- Total (parallel): ~15-20 minutes

**Success Rates:**
- Target: >95% pass rate
- Monitor: Weekly via GitHub Insights
- Alert: If <90% for 3+ days

**Cost Optimization:**
- Use workflow concurrency groups
- Cancel obsolete runs
- Cache dependencies aggressively
- Use appropriate runner sizes

### Health Checks

**Weekly Review Checklist:**
- [ ] Check workflow success rates
- [ ] Review failed workflows
- [ ] Update dependencies (Dependabot)
- [ ] Review security alerts
- [ ] Check action pinning progress
- [ ] Monitor execution times

**Monthly Review Checklist:**
- [ ] Security audit report
- [ ] Update quality thresholds if needed
- [ ] Review and update documentation
- [ ] Team training on new practices
- [ ] Cost analysis and optimization

## Standards Compliance

### Implemented Standards

✅ **SLSA Level 3** - Build provenance and supply chain security  
✅ **OSSF Best Practices** - Security scorecard checks  
✅ **OWASP Top 10** - Security scanning coverage  
✅ **NIST SSDF** - Secure software development framework  
✅ **SPDX/CycloneDX** - SBOM generation  

### Roadmap

**Q1 2026:**
- [ ] Complete action pinning (258 actions)
- [ ] Expand dependency scanning to all languages
- [ ] Add fuzz testing integration
- [ ] Implement security champions program

**Q2 2026:**
- [ ] SLSA Level 4 compliance
- [ ] Advanced threat modeling
- [ ] Automated security patch generation
- [ ] Performance trend dashboard

## Resources

### Internal Documentation
- [PR Testing Guide](./PR_TESTING_GUIDE.md) - Comprehensive testing guide
- [Security Testing](./SECURITY_TESTING.md) - Security standards
- [Workflow Architecture](./PR_WORKFLOW_2025.md) - Technical architecture
- [Contributing Guide](../CONTRIBUTING.md) - General contribution guidelines

### External Resources
- [GitHub Actions Security](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [OSSF Scorecard](https://github.com/ossf/scorecard)
- [SLSA Framework](https://slsa.dev/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Dependabot Docs](https://docs.github.com/en/code-security/dependabot)

### Tools
- **Linting:** ruff, flake8, mypy, yamllint
- **Security:** bandit, semgrep, gitleaks, trufflehog
- **Testing:** pytest, mutmut, hypothesis
- **Coverage:** pytest-cov, coverage.py
- **Performance:** pytest-benchmark, memory-profiler

## Getting Help

**For workflow issues:**
1. Check workflow logs in GitHub Actions
2. Review this document and related guides
3. Search GitHub Issues for similar problems
4. Ask in team Slack #ci-cd channel

**For security concerns:**
1. Review security scan artifacts
2. Check SECURITY.md for reporting process
3. Contact security team directly
4. Never commit secrets - use GitHub Secrets

**For test failures:**
1. Run tests locally to reproduce
2. Check test documentation in TESTING.md
3. Review recent changes to related code
4. Ask for help in code review

---

**Maintained by:** DevSecOps Team  
**Contact:** devops@tradepulse.io  
**Last Review:** 2025-11-15  
**Next Review:** 2025-12-15
