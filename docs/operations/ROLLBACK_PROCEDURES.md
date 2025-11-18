# 🔄 Rollback Procedures & Emergency Response

**Principal System Architect: Production Incident Response**

This document outlines procedures for quickly rolling back changes when regressions or critical issues are detected.

## Quick Reference

| Scenario | Action | Time to Rollback | Risk Level |
|----------|--------|------------------|------------|
| Failed deployment | Revert to previous release | < 5 minutes | 🔴 Critical |
| Breaking API change | Immediate rollback + hotfix | < 10 minutes | 🔴 Critical |
| Performance regression | Investigate → decide | < 30 minutes | 🟠 High |
| Security vulnerability | Hotfix or rollback | < 15 minutes | 🔴 Critical |
| Test failures on main | Revert commit | < 5 minutes | 🟠 High |

## 🚨 Emergency Rollback - Production

### Immediate Actions (< 5 minutes)

```bash
# 1. Identify the problematic deployment/release
git log --oneline -10

# 2. Identify the last known good commit
git log --oneline --before="2 hours ago" -1

# 3. Create emergency rollback branch
git checkout -b emergency/rollback-$(date +%Y%m%d-%H%M%S)

# 4. Revert to last known good state
git revert <bad-commit-sha> --no-edit

# 5. Push and create emergency PR
git push origin HEAD
gh pr create --title "🚨 EMERGENCY ROLLBACK: <description>" \
  --body "**Incident:** <description>
**Root Cause:** <brief description>
**Rollback to:** <good-commit-sha>
**Impact:** <who/what is affected>

See incident log: <link to incident doc>" \
  --label "emergency,rollback" \
  --assignee "@me"
```

### Verification Commands

```bash
# Check CI status
gh run list --branch main --limit 3

# Check workflow status
gh workflow view tests.yml

# Monitor test execution
gh run watch
```

## 📋 Automated Rollback Triggers

The CI system will automatically alert when:

1. **Coverage drops below 98%** - Regression validation workflow
2. **Security issues detected** - Security gate blocks merge
3. **Lint/format failures** - Strict quality gate blocks merge
4. **Breaking changes without label** - Breaking change gate blocks
5. **Dependency vulnerabilities** - Dependency security gate blocks

## 🔧 Quick Rollback Commands

### Revert Last Commit on Main

```bash
# Fast revert for broken main branch
git checkout main
git pull
git revert HEAD --no-edit
git push origin main

# Verify CI runs
gh run watch
```

### Revert Specific Commit

```bash
# Revert specific problematic commit
git revert <commit-sha> --no-edit
git push origin main
```

### Revert Multiple Commits

```bash
# Revert range of commits (oldest..newest)
git revert --no-commit <oldest-bad>^..<newest-bad>
git commit -m "Revert: problematic changes"
git push origin main
```

## 🔍 Post-Rollback Verification

Run these checks after rollback:

```bash
# 1. Verify tests pass
pytest tests/ -v

# 2. Check coverage
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-report=term

# 3. Run security scan
bandit -r core/ backtest/ execution/ -ll

# 4. Check formatting
ruff check .
black --check .

# 5. Verify type checking
mypy core/ backtest/ execution/
```

## 📊 Monitoring After Rollback

Check these workflows for success:

1. **Regression Validation** (`regression-validation.yml`)
2. **PR Quality Gate Strict** (`pr-quality-gate-strict.yml`)
3. **Coverage Analysis** (`coverage-analysis-deep.yml`)
4. **Security Scans** (`security.yml`)
5. **SBOM Generation** (`sbom-enhanced.yml`)

## 📞 Escalation Path

If automated rollback is insufficient:

1. **< 15 min**: On-call engineer attempts rollback
2. **15-30 min**: Escalate to engineering manager
3. **> 30 min**: Involve principal architect + security team
4. **> 1 hour**: Executive notification required

## 📝 Incident Documentation

After rollback, create incident report:

```bash
# Create incident report
cat > docs/incidents/$(date +%Y-%m-%d)-incident.md << 'EOF'
# Incident Report: [Brief Description]

**Date:** $(date +%Y-%m-%d)
**Duration:** [start] - [end]
**Severity:** [Critical/High/Medium/Low]

## Timeline

- **HH:MM** - Issue detected
- **HH:MM** - Rollback initiated
- **HH:MM** - Rollback completed
- **HH:MM** - Service restored

## Root Cause

[Detailed description]

## Impact

[What systems/users were affected]

## Resolution

[How it was fixed]

## Prevention

[Action items to prevent recurrence]

## Action Items

- [ ] [Action 1] - @owner - Due: [date]
- [ ] [Action 2] - @owner - Due: [date]

EOF
```

## 🛡️ Prevention: Quality Gates

Our CI now enforces these **BLOCKING** checks on all PRs:

### 1. Formatting & Linting Gate
- ✅ Ruff linting
- ✅ Black formatting
- ✅ isort import sorting
- ✅ mypy type checking

### 2. Security Gate
- ✅ Bandit security scan
- ✅ detect-secrets scan
- ✅ Hardcoded credential check

### 3. Coverage Gate
- ✅ 98% minimum coverage
- ✅ No coverage regression

### 4. Dependency Security Gate
- ✅ pip-audit CVE check
- ✅ Security constraints verification

### 5. Breaking Change Gate
- ✅ Public API change detection
- ✅ Migration documentation required

**All gates must pass before merge is allowed.**

## 🚀 Safe Deployment Practices

To minimize need for rollbacks:

1. **Use PR quality gates** - All PRs must pass strict checks
2. **Run regression validation** - Automated critical path testing
3. **Monitor coverage trends** - Weekly deep coverage analysis
4. **Track dependencies** - Daily SBOM + vulnerability scans
5. **Document breaking changes** - Required migration guides

## 📚 Related Documentation

- [Regression Validation Workflow](../../.github/workflows/regression-validation.yml)
- [PR Quality Gates](../../.github/workflows/pr-quality-gate-strict.yml)
- [Coverage Analysis](../../.github/workflows/coverage-analysis-deep.yml)
- [SBOM Generation](../../.github/workflows/sbom-enhanced.yml)

---

**Last Updated:** 2025-11-18
**Maintained By:** Principal System Architect
**Review Frequency:** Monthly
