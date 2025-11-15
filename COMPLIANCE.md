# Compliance & Quality Gates Policy

**Version:** 1.0  
**Effective Date:** 2025-11-15  
**Last Updated:** 2025-11-15

## Overview

This document describes TradePulse's comprehensive compliance and quality gate policies for CI/CD pipelines. These policies balance quality assurance with development velocity through ratchet-based progression rather than absolute thresholds.

## Philosophy: Ratchet over Absolute Thresholds

Traditional quality gates use absolute thresholds (e.g., "98% coverage required"), which can:
- Block legitimate changes that improve overall quality but don't meet historical high bars
- Penalize new features for existing technical debt
- Create perverse incentives to game metrics

**TradePulse uses ratchet policies instead:**
- **No Regression Rule:** New changes must not decrease quality metrics
- **Baseline Tracking:** Current quality level becomes the minimum for future changes
- **Soft Thresholds:** New code without baselines gets warnings, not blocks
- **Progressive Improvement:** Quality naturally increases over time

## Quality Gate Policies

### 1. License Compliance

**Policy:** Prevent copyleft and restrictive licenses that conflict with commercial use.

**Enforcement:**
- ✅ **ALLOW:** MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MPL-2.0, LGPL-3.0-or-later
- ❌ **DENY:** GPL-3.0-only, AGPL-3.0, SSPL-1.0
- ⚠️ **REVIEW:** All other licenses (manual approval required)

**Actions:**
- DENY licenses → FAIL build
- REVIEW licenses → WARN (doesn't block PR)
- All licenses → Generate SBOM artifacts

**Reference:** [License Policy](docs/compliance/license-policy.md)

**Workflow:** `.github/workflows/dependency-review.yml`

---

### 2. Security Policy Enforcement (OPA)

**Policy:** Enforce secure coding practices and workflow security at two severity levels.

**Enforcement:**

#### HIGH/CRITICAL (DENY - Blocks PR)
- `permissions: write-all` without justification
- Unsafe `pull_request_target` with PR code execution
- Unpinned actions in security-sensitive workflows (handling secrets/write permissions)

#### MEDIUM/LOW (WARN - Doesn't block)
- Missing explicit `permissions:` block
- Missing `timeout-minutes`
- Missing `concurrency:` control

**Actions:**
- HIGH/CRITICAL violations → FAIL build
- MEDIUM/LOW issues → WARN in PR comment

**Reference:** [Workflow Security Policy](docs/compliance/workflow-security.md)

**Workflow:** `.github/workflows/security-policy-enforcement.yml`

---

### 3. Code Coverage

**Policy:** Prevent coverage regression using ratchet logic.

**Enforcement:**

#### With Baseline
- **Rule:** `coverage_current >= coverage_baseline - 0.5%`
- **Per-File:** Changed files must have ≥80% coverage
- **Action:** FAIL if regression exceeds 0.5%

#### Without Baseline (New Code)
- **Soft Threshold:** 70% coverage
- **Action:** WARN if below 70%, doesn't block

**Baseline Management:**
- Stored as artifact for 90 days
- Updated on successful merge to main/develop
- Separate baselines per branch

**Reference:** Coverage report in PR comments

**Workflow:** `.github/workflows/coverage.yml`

---

### 4. Mutation Testing

**Policy:** Ensure test quality doesn't regress using mutation kill rate.

**Enforcement:**

#### With Baseline
- **Rule:** `kill_rate_current >= kill_rate_baseline`
- **Scope:** Only changed modules are tested (for speed)
- **Action:** FAIL if kill rate decreases

#### Without Baseline (New Code)
- **Soft Threshold:** 70% kill rate
- **Action:** WARN if below 70%, doesn't block

**Optimization:**
- Mutation testing runs only on changed modules in PRs
- Full mutation testing on main/develop pushes
- Baseline stored for 90 days

**Reference:** Mutation report in PR comments

**Workflow:** `.github/workflows/mutation-testing.yml`

---

### 5. SBOM & Vulnerability Analysis

**Policy:** Prevent new critical/high vulnerabilities while tracking existing ones.

**Enforcement:**

#### With Baseline
- **Rule:** No NEW Critical or High vulnerabilities vs baseline
- **Action:** FAIL if new Critical/High detected
- **Existing:** Tracked in VULNERABILITY_BACKLOG.md, doesn't block

#### Without Baseline (Initial Scan)
- All vulnerabilities become baseline
- Tracked in VULNERABILITY_BACKLOG.md
- No PR blocking

**Vulnerability Management:**
- Critical/High: Fixed within 30 days
- Medium: Fixed within 90 days
- Low: Fixed within 180 days
- Quarterly reviews of backlog

**Reference:** [Vulnerability Backlog](VULNERABILITY_BACKLOG.md)

**Workflow:** `.github/workflows/sbom-generation.yml`

---

### 6. Merge Guard & Label Management

**Policy:** Coordinate all quality gates and manage PR labels automatically.

**Features:**

#### Automatic Label Management
- **`missing-coverage`:** Auto-added when new files lack tests
- **Auto-removal:** Removed when tests are added
- **Critical PR exemption:** Label doesn't block security/hotfix/critical PRs

#### Quality Gate Coordination
- Monitors coverage and mutation ratchet results
- Aggregates all quality signals
- Provides single source of truth for merge readiness

**Reference:** Merge Guard status in PR comments

**Workflow:** `.github/workflows/merge-guard.yml`

---

## Baseline Management

### Artifact Storage
- All baselines stored as GitHub Actions artifacts
- Retention: 90 days
- Storage trigger: Successful push to main/develop

### Baseline Types
1. **Coverage:** `coverage.json`, `coverage.xml`
2. **Mutation:** `mutation_summary.json`
3. **Vulnerabilities:** `grype-sbom-report.json`

### Baseline Updates
- Automatic on merge to main/develop
- Triggered by workflow success
- No manual intervention required

### Baseline Expiry
- After 90 days, artifacts expire
- Next run establishes new baseline with soft thresholds
- Prevents stale baselines from blocking development

---

## Policy Evolution

### When to Use Absolute Thresholds

Ratchet policies work best for mature codebases. Use absolute thresholds when:
- Starting a new project (set initial quality bar)
- After major refactoring (reset baseline)
- For critical security requirements (e.g., authentication code must have 95% coverage)

### Adjusting Ratchet Sensitivity

Current settings:
- **Coverage regression:** 0.5% tolerance
- **Mutation regression:** 0% tolerance (no regression)
- **Per-file coverage:** 80% for changed files

These can be adjusted in workflow files if too strict/lenient.

### Temporary Waivers

For exceptional circumstances:
1. Add explicit waiver in PR description
2. Requires security team approval for security-related gates
3. Document in appropriate tracking file (e.g., VULNERABILITY_BACKLOG.md)

---

## Monitoring and Metrics

### Quality Trends

Track over time:
- Average coverage per commit
- Mutation kill rate trend
- Vulnerability remediation rate
- Gate pass/fail rates

### Dashboard (Future)

Planned metrics dashboard showing:
- Current baseline levels
- Historical trends
- Per-module quality scores
- Technical debt tracking

---

## Compliance Reporting

### Audit Trail

All quality gate decisions are:
- Logged in workflow runs
- Commented on PRs with full context
- Stored in artifacts for 90 days
- Available for compliance audits

### Documentation Trail

- License decisions → `docs/compliance/license-policy.md`
- Security decisions → `docs/compliance/workflow-security.md`
- Vulnerability tracking → `VULNERABILITY_BACKLOG.md`
- Security incidents → `SECURITY_FIXES.md`

---

## Emergency Procedures

### Bypassing Gates for Critical Fixes

For critical security fixes or production incidents:

1. Label PR with `security` or `hotfix` or `critical`
2. Missing coverage label won't block (but still tracks)
3. All other gates still apply (security, licenses)
4. Document bypass reason in PR
5. Create follow-up issue for missing tests

### Disabling Gates Temporarily

In case of false positives or tool failures:

1. Disable specific check in branch protection (admin access required)
2. Document reason in issue
3. Fix root cause
4. Re-enable check
5. Document incident in SECURITY_FIXES.md

---

## Version History

| Version | Date       | Changes                                               |
|---------|------------|-------------------------------------------------------|
| 1.0     | 2025-11-15 | Initial compliance policy with ratchet methodology    |

---

## References

- [License Policy](docs/compliance/license-policy.md)
- [Workflow Security Policy](docs/compliance/workflow-security.md)
- [Vulnerability Backlog](VULNERABILITY_BACKLOG.md)
- [Security Policy](SECURITY.md)

---

*For questions about compliance policies, contact the engineering team via GitHub issues with the `compliance` label.*
