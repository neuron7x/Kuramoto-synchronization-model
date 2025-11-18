# ADR-0004: Comprehensive CI/CD Regression Testing & Quality Gates

**Status:** Accepted  
**Date:** 2025-11-18  
**Authors:** Principal System Architect  
**Deciders:** Engineering Leadership, DevOps Team  

## Context

The TradePulse repository is undergoing significant technical work including security hardening, tech debt reduction, and CI/CD improvements. With large-scale changes being made, there is a critical need to:

1. **Prevent Regressions**: Ensure that large changes don't introduce breaking changes or quality degradation
2. **Maintain Quality Standards**: Enforce consistent code quality, test coverage, and security standards
3. **Enable Fast Rollbacks**: Provide clear procedures and automation for quick incident response
4. **Track Dependencies**: Comprehensive SBOM generation and vulnerability monitoring
5. **Improve Visibility**: Better reporting and analysis of code coverage and quality metrics

### Current State

The repository already has strong CI/CD foundations:
- 47 GitHub Actions workflows
- Existing coverage tracking (98% threshold)
- Security scanning workflows
- SBOM generation capabilities
- Mutation testing
- Merge guards

### Problems

1. **Regression Detection**: No dedicated regression test suite for critical paths
2. **Quality Gate Enforcement**: Quality checks exist but aren't strictly enforced as blockers
3. **Coverage Blind Spots**: Need better visibility into which critical code lacks tests
4. **Rollback Procedures**: No formalized, documented rollback procedures
5. **SBOM Gaps**: SBOM generation lacks vulnerability tracking and trend analysis

## Decision

We will implement a comprehensive **Principal System Architect-level** CI/CD enhancement consisting of:

### 1. Regression Validation Suite (`regression-validation.yml`)

**Purpose:** Dedicated workflow to validate critical paths haven't regressed

**Components:**
- Critical path testing matrix (execution, market feed, backtest, risk, orders)
- Coverage regression detection with module-level analysis
- Security regression scanning
- Automated regression summary reporting

**Triggers:**
- All pushes to `main`
- All PRs to `main` and `develop`
- Must pass before merge

**Key Features:**
- Fail-fast on any critical path failure
- PR comments with detailed coverage reports
- Upload test artifacts for forensic analysis

### 2. Strict PR Quality Gates (`pr-quality-gate-strict.yml`)

**Purpose:** Zero-tolerance quality enforcement on all PRs

**Mandatory Gates (All Must Pass):**

#### Gate 1: Formatting & Linting
- ✅ Ruff linting (no errors allowed)
- ✅ Black formatting (must be formatted)
- ✅ isort import sorting (must be sorted)
- ✅ mypy type checking (no type errors)

#### Gate 2: Security Scanning
- ✅ Bandit security scan (no high/critical issues)
- ✅ detect-secrets scan (no secrets in code)
- ✅ Hardcoded credential detection

#### Gate 3: Coverage Threshold
- ✅ Minimum 98% coverage maintained
- ✅ No coverage regression allowed

#### Gate 4: Dependency Security
- ✅ pip-audit passes (no vulnerable dependencies)
- ✅ Security constraints file validated

#### Gate 5: Breaking Change Detection
- ✅ Public API changes flagged
- ✅ Breaking changes require label + migration docs

**Enforcement:** PRs CANNOT be merged until all gates pass

### 3. Deep Coverage Analysis (`coverage-analysis-deep.yml`)

**Purpose:** Proactive identification of test coverage gaps

**Features:**
- Module-level coverage analysis with priority classification
- Top 20 critical test recommendations
- Untested critical function identification
- Coverage heatmap generation
- Weekly automated issue creation with recommendations

**Schedule:** Weekly on Sundays + on-demand

**Outputs:**
- Detailed coverage gap report (markdown)
- Test recommendations (JSON)
- Untested functions list (JSON)
- Coverage heatmap visualization

### 4. Enhanced SBOM & Dependency Health (`sbom-enhanced.yml`)

**Purpose:** Complete supply chain visibility and security

**Features:**
- Multi-ecosystem SBOM generation (Python, Go, npm, Rust)
- CycloneDX and SPDX format support
- Vulnerability scanning with Grype
- Severity analysis and trending
- Dependency freshness checking
- Automatic issue creation for critical vulnerabilities

**Schedule:** Daily at 02:00 UTC + on release + on-demand

**Artifacts:**
- SBOM files (multiple formats)
- Vulnerability reports (JSON + markdown)
- Dependency health metrics
- Historical SBOM archive

### 5. Rollback Procedures Documentation

**Purpose:** Fast incident response and recovery

**Location:** `docs/operations/ROLLBACK_PROCEDURES.md`

**Coverage:**
- Emergency rollback procedures (< 5 min target)
- Verification commands and checklists
- Monitoring and escalation paths
- Incident documentation templates
- Prevention strategies

## Consequences

### Positive

1. **Regression Prevention**: Automated detection before changes reach main
2. **Quality Assurance**: Strict enforcement ensures consistent high quality
3. **Fast Recovery**: Clear rollback procedures minimize incident duration
4. **Security Posture**: Comprehensive vulnerability tracking and alerting
5. **Developer Confidence**: Clear feedback on what needs fixing
6. **Continuous Improvement**: Weekly coverage analysis drives test growth
7. **Supply Chain Security**: Complete SBOM tracking with vulnerability management

### Negative

1. **CI Runtime**: Additional workflows increase total CI time
2. **Developer Friction**: Strict gates may slow down some PRs
3. **Maintenance Overhead**: More workflows to maintain and update
4. **Initial Setup**: Requires team training on new procedures

### Mitigations

1. **Parallel Execution**: Workflows run in parallel where possible
2. **Clear Feedback**: Detailed error messages guide developers to fixes
3. **Documentation**: Comprehensive docs reduce confusion
4. **Incremental Rollout**: Can enable gates gradually if needed

## Implementation Plan

### Phase 1: Core Workflows (Week 1)
- [x] Create regression validation workflow
- [x] Create strict PR quality gate workflow
- [x] Create coverage analysis workflow
- [x] Create enhanced SBOM workflow
- [ ] Test workflows on sample PRs

### Phase 2: Documentation (Week 1)
- [x] Create rollback procedures document
- [x] Create ADR for decisions
- [ ] Update team runbooks
- [ ] Create training materials

### Phase 3: Branch Protection (Week 2)
- [ ] Configure branch protection rules
- [ ] Make quality gates required status checks
- [ ] Set up automated enforcement

### Phase 4: Monitoring (Week 2-3)
- [ ] Monitor workflow reliability
- [ ] Gather developer feedback
- [ ] Tune thresholds as needed
- [ ] Create dashboards for metrics

### Phase 5: Continuous Improvement (Ongoing)
- [ ] Weekly review of coverage recommendations
- [ ] Monthly review of security alerts
- [ ] Quarterly review of rollback procedures
- [ ] Regular workflow optimization

## Metrics

We will track:

1. **Regression Detection**
   - Number of regressions caught before merge
   - Time to detect regressions
   - False positive rate

2. **Quality Metrics**
   - PR pass rate on first attempt
   - Average time to pass all gates
   - Coverage trend over time

3. **Security Metrics**
   - Critical vulnerabilities found
   - Mean time to remediate (MTTR)
   - Dependency update frequency

4. **Incident Response**
   - Rollback frequency
   - Time to rollback (target: < 5 min)
   - Incident resolution time

## Alternatives Considered

### Alternative 1: Keep Existing CI As-Is

**Pros:**
- No changes needed
- No additional CI time
- No developer friction

**Cons:**
- Regressions continue to slip through
- Quality varies by PR
- No proactive coverage improvement
- Reactive incident response

**Decision:** Rejected - insufficient given scale of changes

### Alternative 2: Manual Code Review Only

**Pros:**
- Flexible
- Human judgment
- No automation complexity

**Cons:**
- Doesn't scale
- Inconsistent quality
- Reviewers miss issues
- No metrics/trending

**Decision:** Rejected - too slow and error-prone

### Alternative 3: External CI/CD Platform

**Pros:**
- More features
- Better UI
- Professional support

**Cons:**
- Additional cost
- Migration effort
- Less integration with GitHub
- Learning curve

**Decision:** Rejected - GitHub Actions sufficient

## References

- [GitHub Actions Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [SBOM Standards (CycloneDX)](https://cyclonedx.org/)
- [OSSF Scorecard](https://github.com/ossf/scorecard)
- [Google SRE Book - Incident Management](https://sre.google/sre-book/incident-response/)

## Notes

- This ADR supersedes informal CI/CD practices
- All new workflows follow GitHub Actions best practices
- Security scanning uses industry-standard tools
- SBOM generation follows NTIA minimum elements standard

---

**Review Date:** 2025-12-18  
**Next Review:** Quarterly or when major changes needed
