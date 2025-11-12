# PR Testing & Quality Standards Guide - 2025

> **World-Leading Best Practices for Pull Request Quality Assurance**

This guide outlines the comprehensive PR testing methodology implemented in TradePulse, aligned with 2025 industry standards from organizations like CNCF, OSSF, SLSA, and major tech companies (Google, Microsoft, Meta).

## Table of Contents
- [Overview](#overview)
- [Automated Quality Gates](#automated-quality-gates)
- [Security Standards](#security-standards)
- [Supply Chain Security](#supply-chain-security)
- [Testing Levels](#testing-levels)
- [Performance Standards](#performance-standards)
- [Code Quality Metrics](#code-quality-metrics)
- [CI/CD Pipeline Security](#cicd-pipeline-security)
- [Troubleshooting](#troubleshooting)

## Overview

Every PR in TradePulse undergoes a multi-layered quality assurance process designed to ensure:
- **Security**: Zero critical vulnerabilities make it to production
- **Reliability**: 98%+ code coverage with 90%+ mutation kill rate
- **Performance**: No regressions >10% in critical paths
- **Compliance**: License compliance and supply chain security
- **Maintainability**: Manageable complexity and clear ownership

## Automated Quality Gates

### 1. Code Coverage Gate
- **Threshold**: ≥98% line coverage
- **Tools**: pytest-cov with sharding
- **Workflow**: `ci.yml`
- **Enforcement**: Blocks merge if below threshold

```yaml
# Runs automatically on every PR
- Code coverage must be ≥98%
- Critical modules (core, backtest, execution) specially monitored
- Sharded execution (3 shards) for performance
```

### 2. Mutation Testing Gate
- **Threshold**: ≥90% mutation kill rate
- **Tools**: mutmut
- **Workflow**: `ci.yml`
- **Purpose**: Ensures tests actually catch bugs

```yaml
# Validates test effectiveness
- Introduces mutations (code changes)
- Tests must fail on 90%+ of mutations
- Prevents "useless" tests
```

### 3. Security Scanning
Multiple layers of security validation:

#### Static Analysis
- **Bandit**: Python security linter
- **Semgrep**: Multi-language security patterns
- **CodeQL**: Advanced semantic analysis (Python, JS, Go)

#### Secret Scanning
- **Gitleaks**: Git history scanning
- **TruffleHog**: Verified secret detection
- **detect-secrets**: Pre-commit hook

#### Dependency Scanning
- **Safety**: Known vulnerabilities in Python packages
- **pip-audit**: OSV database scanning
- **Grype**: SBOM-based vulnerability detection
- **Trivy**: Container and filesystem scanning

#### Container Security
- **Trivy**: Critical CVE detection
- **Grype**: Multi-source vulnerability DB
- **SBOM**: Generated and signed for every build

### 4. SLSA Provenance
- **Level**: SLSA Level 3 compliance
- **Tool**: GitHub Attestations + Sigstore
- **Workflow**: `slsa-provenance.yml`
- **Purpose**: Build integrity and supply chain security

```yaml
Features:
- Build provenance generation
- Keyless signing with Sigstore/Cosign
- Attestation stored in GitHub
- Verification available via slsa-verifier
```

### 5. OSSF Scorecard
- **Tool**: OSSF Scorecard
- **Workflow**: `ossf-scorecard.yml`
- **Frequency**: Weekly + on every PR to main
- **Checks**: 18+ security best practices

```yaml
Key Checks:
- Branch protection enabled
- Security policy present
- Dependency pinning
- CI/CD security
- Code review requirements
- Signed commits (recommended)
```

### 6. SBOM Generation
- **Standards**: SPDX 2.3, CycloneDX 1.5
- **Tools**: Syft, CycloneDX Python
- **Workflow**: `sbom-generation.yml`
- **Signing**: Sigstore keyless signing

```yaml
Deliverables:
- SPDX JSON SBOM
- CycloneDX JSON SBOM
- VEX (Vulnerability Exploitability eXchange)
- Signed with Sigstore
- Attestation via GitHub API
```

### 7. License Compliance
- **Tools**: pip-licenses, licensecheck
- **Workflow**: `dependency-review.yml`
- **Allowed**: MIT, Apache-2.0, BSD-2/3-Clause, ISC, MPL-2.0
- **Prohibited**: GPL-3.0, AGPL-3.0, SSPL

```yaml
Checks:
- License compatibility
- Dependency confusion protection
- Malicious package detection
- Public package conflicts
```

### 8. Performance Regression Detection
- **Tools**: pytest-benchmark, memory-profiler
- **Workflow**: `performance-regression-pr.yml`
- **Thresholds**: 
  - Warning: >10% slowdown
  - Failure: >25% slowdown
  - Memory: >20% increase

```yaml
Process:
1. Benchmark PR changes
2. Benchmark base branch
3. Compare results
4. Report regressions
5. Block critical regressions (>25%)
```

### 9. PR Complexity Analysis
- **Tools**: radon, lizard, cloc
- **Workflow**: `pr-complexity-analysis.yml`
- **Metrics**:
  - Lines changed (<500 preferred)
  - Files changed (<20 preferred)
  - Cyclomatic complexity (avg <10, max <15)

```yaml
Risk Scoring:
- Size risk (lines and files)
- Complexity risk (cyclomatic)
- Breaking change detection
- Code ownership verification
```

### 10. Security Policy Enforcement (OPA)
- **Tool**: Open Policy Agent (OPA)
- **Workflow**: `security-policy-enforcement.yml`
- **Policies**: Rego-based security rules

```yaml
Enforced Policies:
1. Secrets Detection
   - No hardcoded passwords
   - No API keys
   - No tokens

2. Secure Coding
   - No SQL injection patterns
   - No eval() usage
   - No unsafe pickle.loads()
   - No subprocess shell=True
   - Use secrets module for tokens

3. Dependency Security
   - Dependencies must be pinned
   - No known vulnerable versions

4. Container Security
   - Non-root USER required
   - No :latest tags
   - HEALTHCHECK required
```

### 11. CI/CD Pipeline Hardening
- **Tool**: actionlint + custom audits
- **Workflow**: `ci-hardening.yml`
- **Standards**: GitHub Actions security best practices

```yaml
Checks:
- Workflow linting (actionlint)
- Action pinning verification (must use SHA)
- Permission minimization
- Dangerous pattern detection
- OIDC token usage validation
- No pull_request_target with code execution
- No script injection vulnerabilities
```

## Security Standards

### OWASP Top 10 Protection
1. **Injection**: SQL, command, eval prevention
2. **Broken Authentication**: No hardcoded credentials
3. **Sensitive Data Exposure**: Secret scanning, encryption
4. **XXE**: XML parsing safety
5. **Broken Access Control**: RBAC validation
6. **Security Misconfiguration**: Container hardening
7. **XSS**: Input validation
8. **Insecure Deserialization**: Pickle safety
9. **Known Vulnerabilities**: Dependency scanning
10. **Insufficient Logging**: Audit logging

### CWE/SANS Top 25
- CWE-79: XSS
- CWE-89: SQL Injection
- CWE-78: OS Command Injection
- CWE-20: Input Validation
- CWE-22: Path Traversal
- CWE-352: CSRF
- CWE-434: File Upload
- CWE-502: Deserialization
- And 17 more...

## Supply Chain Security

### SLSA Framework
- **Level 3**: Build provenance, isolated builds, signed artifacts
- **Provenance**: Generated for every build
- **Verification**: Available via slsa-verifier CLI

### Sigstore Integration
- **Keyless Signing**: No key management overhead
- **Cosign**: Artifact signing
- **Rekor**: Transparency log
- **Fulcio**: Certificate authority

### Dependency Security
- **Pinning**: All dependencies pinned to exact versions
- **Scanning**: Multiple vulnerability databases
- **Confusion Protection**: Internal package name checking
- **Updates**: Automated via Dependabot (weekly)

## Testing Levels

### L0: Static Analysis
- Pre-execution validation
- Syntax checking
- Linting (ruff, flake8, mypy)
- Secret scanning

### L1: Unit Tests
- Hermetic, no I/O
- Fast execution (<1s each)
- 98%+ coverage required
- Property-based testing (Hypothesis)

### L2: Contract Tests
- Schema validation
- API contracts
- OpenAPI compliance
- RBAC rules

### L3: Integration Tests
- Module interaction
- End-to-end workflows
- Database integration
- External service mocking

### L4: E2E Regression
- Full pipeline testing
- Production-like environment
- Performance validation
- Data quality gates

### L5: Chaos & Resilience
- Fault injection
- Graceful degradation
- Recovery testing
- Thermodynamic validation

### L6: Infrastructure Readiness
- Deployment validation
- Configuration verification
- Environment conformance
- Helm chart testing

### L7: UI/UX Quality
- Playwright E2E
- Accessibility (aXe)
- Visual regression
- Signal rendering

## Performance Standards

### Benchmarking Strategy
1. **Critical Path Identification**
   - Order execution
   - Market data processing
   - Strategy computation

2. **Baseline Establishment**
   - Base branch benchmarks
   - Historical trend analysis
   - Platform-specific baselines

3. **Regression Detection**
   - Statistical significance
   - Multi-run averaging (5+ runs)
   - Outlier detection

4. **Thresholds**
   - 🟢 <10%: Acceptable variance
   - 🟡 10-25%: Requires justification
   - 🔴 >25%: Blocks merge

### Memory Profiling
- Baseline vs PR comparison
- Memory leak detection
- Peak usage monitoring
- Allocation pattern analysis

## Code Quality Metrics

### Coverage Requirements
- **Line Coverage**: ≥98%
- **Branch Coverage**: ≥95%
- **Critical Modules**: 100%

### Complexity Limits
- **Cyclomatic Complexity**:
  - Average: <10
  - Maximum: <15
- **Cognitive Complexity**: <20
- **Nesting Depth**: <4

### PR Size Guidelines
- **Ideal**: <250 lines
- **Acceptable**: <500 lines
- **Large**: 500-1000 lines (requires justification)
- **Too Large**: >1000 lines (break into smaller PRs)

### Code Ownership
- **Coverage**: 100% of changed files
- **Review**: Required from CODEOWNERS
- **Documentation**: Updated for ownership changes

## CI/CD Pipeline Security

### Workflow Security Best Practices
1. **Minimal Permissions**
   ```yaml
   permissions:
     contents: read
     pull-requests: write
   ```

2. **Action Pinning**
   ```yaml
   # Bad
   uses: actions/checkout@v5
   
   # Good
   uses: actions/checkout@a81bbbf8298c0fa03ea29cdc473d45769f953675
   ```

3. **OIDC Authentication**
   ```yaml
   permissions:
     id-token: write
   # Use OIDC instead of long-lived credentials
   ```

4. **Avoid pull_request_target**
   - Don't checkout PR code in pull_request_target
   - Use pull_request trigger instead
   - Separate untrusted code execution

5. **Input Validation**
   - Never trust github.event.* in scripts
   - Use environment variables
   - Validate all inputs

### Secret Management
- **GitHub Secrets**: For CI/CD credentials
- **Environment Secrets**: For environment-specific values
- **Vault Integration**: For production secrets
- **Rotation**: Regular credential rotation (90 days)

## Troubleshooting

### Coverage Failures
**Symptom**: Coverage below 98%
**Solutions**:
1. Add tests for uncovered lines
2. Remove dead code
3. Mark test-only code with # pragma: no cover
4. Check coverage report: `coverage html`

### Mutation Testing Failures
**Symptom**: Kill rate below 90%
**Solutions**:
1. Strengthen test assertions
2. Add edge case tests
3. Remove redundant tests
4. Review mutmut report: `mutmut results`

### Security Scan Failures
**Symptom**: Critical vulnerabilities detected
**Solutions**:
1. Update vulnerable dependencies
2. Apply security patches
3. Use constraints/security.txt for pinning
4. Request CVE exceptions (with justification)

### Performance Regressions
**Symptom**: >10% slowdown detected
**Solutions**:
1. Profile the code: `python -m cProfile`
2. Optimize hot paths
3. Add caching where appropriate
4. Use more efficient algorithms
5. Document necessary trade-offs

### License Compliance Issues
**Symptom**: Prohibited license detected
**Solutions**:
1. Replace package with alternative
2. Contact legal for exception
3. Implement functionality internally
4. Request vendor to relicense

### Complexity Issues
**Symptom**: High cyclomatic complexity
**Solutions**:
1. Extract methods/functions
2. Use early returns
3. Simplify conditional logic
4. Apply design patterns (Strategy, Factory)

## Additional Resources

### Standards & Frameworks
- [SLSA](https://slsa.dev/) - Supply-chain Levels for Software Artifacts
- [OSSF](https://openssf.org/) - Open Source Security Foundation
- [OWASP](https://owasp.org/) - Open Web Application Security Project
- [CWE](https://cwe.mitre.org/) - Common Weakness Enumeration
- [NIST SSDF](https://csrc.nist.gov/Projects/ssdf) - Secure Software Development Framework

### Tools Documentation
- [pytest](https://docs.pytest.org/)
- [mutmut](https://mutmut.readthedocs.io/)
- [Bandit](https://bandit.readthedocs.io/)
- [Semgrep](https://semgrep.dev/docs/)
- [CodeQL](https://codeql.github.com/docs/)
- [Trivy](https://aquasecurity.github.io/trivy/)
- [Syft](https://github.com/anchore/syft)
- [Cosign](https://docs.sigstore.dev/cosign/)
- [OPA](https://www.openpolicyagent.org/docs/)

### Internal Documentation
- [TESTING.md](../TESTING.md) - Testing strategy
- [SECURITY.md](../SECURITY.md) - Security policy
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guide
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) - Community standards

---

**Questions or Issues?**
- File an issue on GitHub
- Contact the security team
- Review workflow logs for details
- Check artifact reports for deep analysis

**Last Updated**: 2025-11-11
**Version**: 2.0
**Maintained by**: TradePulse DevSecOps Team
