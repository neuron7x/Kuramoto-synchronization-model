# Security Testing Standards - 2025

> **Comprehensive Security Testing Framework for GeoSync**

## Overview

This document outlines the security testing standards and practices implemented in GeoSync, aligned with industry-leading frameworks including OWASP, NIST SSDF, SLSA, and OSSF best practices.

## Table of Contents
1. [Security Testing Layers](#security-testing-layers)
2. [Automated Security Scans](#automated-security-scans)
3. [Supply Chain Security](#supply-chain-security)
4. [Vulnerability Management](#vulnerability-management)
5. [Security Gates](#security-gates)
6. [Incident Response](#incident-response)

## Security Testing Layers

### Layer 1: Static Analysis (Pre-Commit)
**Frequency**: Every commit
**Tools**: detect-secrets, pre-commit hooks
**Purpose**: Catch security issues before they enter version control

```bash
# Pre-commit hooks automatically run:
- detect-secrets: Baseline secret scanning
- gitleaks: Git history secret detection
- shellcheck: Shell script security
- mypy: Type safety (prevents type confusion)
```

### Layer 2: SAST (Pull Request)
**Frequency**: Every PR
**Tools**: Bandit, Semgrep, CodeQL
**Purpose**: Deep static analysis of code patterns

#### Bandit (Python)
- **Severity**: High, Medium, Low
- **Rules**: 150+ Python-specific security checks
- **Blocking**: High/Critical findings

#### Semgrep
- **Languages**: Python, JavaScript, TypeScript, Go, Rust
- **Rules**: OWASP Top 10, CWE Top 25, custom rules
- **Mode**: PR scanning with auto-fix suggestions

#### CodeQL
- **Query Packs**: security-extended
- **Languages**: Python, JavaScript, Go
- **Integration**: GitHub Security tab

### Layer 3: Secret Scanning (Continuous)
**Frequency**: Every push, PR
**Tools**: Gitleaks, TruffleHog, detect-secrets
**Purpose**: Prevent credential exposure

**Gitleaks Configuration:**
```toml
[extend]
useDefault = true

[allowlist]
description = "Known false positives"
paths = [
  ".secrets.baseline"
]
```

**TruffleHog:**
- Verified secrets only (--only-verified)
- Git history scanning
- Real-time alerts

### Layer 4: Dependency Scanning (Daily/PR)
**Frequency**: Daily + every dependency change
**Tools**: Safety, pip-audit, Grype, Trivy
**Purpose**: Identify vulnerable dependencies

**Vulnerability Sources:**
- OSV (Open Source Vulnerabilities)
- NVD (National Vulnerability Database)
- GitHub Advisory Database
- PyPA Advisory Database

**Threshold:**
- Critical: Block PR
- High: Warning + review required
- Medium/Low: Track for remediation

### Layer 5: Container Scanning (Build Time)
**Frequency**: Every container build
**Tools**: Trivy, Grype
**Purpose**: Secure container images

**Checks:**
- Base image vulnerabilities
- Application dependencies
- Misconfigurations
- Secrets in layers

**Standards:**
- Non-root user required
- No :latest tags
- HEALTHCHECK defined
- Minimal attack surface

### Layer 6: SBOM Generation & Attestation
**Frequency**: Every build
**Tools**: Syft, CycloneDX, Sigstore
**Purpose**: Supply chain transparency

**Deliverables:**
- SPDX 2.3 SBOM
- CycloneDX 1.5 SBOM
- VEX document
- Sigstore signatures
- GitHub attestations

### Layer 7: Runtime Security (Production)
**Tools**: Falco, AppArmor/SELinux
**Purpose**: Runtime threat detection

## Automated Security Scans

### Workflow: Security Scan (`security.yml`)

#### Secret Scanning
```yaml
jobs:
  secret-scan:
    - Custom secret scanner (core.utils.security)
    - Gitleaks (Git history)
    - TruffleHog (verified secrets)
    - Bandit (hardcoded credentials)
```

**Exit Criteria:**
- No verified secrets found
- All findings in .secrets.baseline
- Custom patterns validated

#### Dependency Scanning
```yaml
jobs:
  dependency-scan:
    - Safety (PyPA advisories)
    - pip-audit (OSV database)
    - Known vulnerability filtering
    - Exception handling (documented)
```

**Exit Criteria:**
- No critical vulnerabilities
- High vulnerabilities documented
- Exceptions approved by security team

#### Container Scanning
```yaml
jobs:
  container-scan:
    - Trivy (critical CVEs)
    - Grype (multi-source)
    - SARIF upload to GitHub Security
    - Dual-scanner validation
```

**Exit Criteria:**
- No critical CVEs in both scanners
- Documented exceptions for false positives
- Base images up-to-date

### Workflow: Semgrep (`semgrep.yml`)

**Configuration:**
- Auto config (Python, TS, Rust, Go)
- Severity: ERROR, WARNING
- SARIF output to Security tab
- Fail on critical findings

**Rule Sets:**
- OWASP Top 10
- CWE Top 25
- Language-specific security patterns
- Custom GeoSync rules

### Workflow: CodeQL (`security.yml`)

**Matrix:**
- Python (primary)
- JavaScript (frontend)
- Go (infrastructure)

**Query Packs:**
- security-extended
- security-and-quality

**Integration:**
- GitHub Security tab
- PR annotations
- Trending analysis

## Supply Chain Security

### SLSA Level 3 Compliance

**Requirements Met:**
✅ Build provenance generation
✅ Isolated build environment (GitHub Actions)
✅ Parameterless builds
✅ Signed artifacts (Sigstore)
✅ Build service attestation

**Verification:**
```bash
# Verify SLSA provenance
slsa-verifier verify-artifact \
  --provenance-path provenance.json \
  --source-uri github.com/neuron7xLab/GeoSync
```

### OSSF Scorecard

**Checks (18+):**
1. ✅ Branch Protection
2. ✅ CI Tests
3. ✅ CII Best Practices Badge
4. ✅ Code Review
5. ✅ Contributors
6. ✅ Dangerous Workflow
7. ✅ Dependency Update Tool
8. ✅ Fuzzing
9. ✅ License
10. ✅ Maintained
11. ✅ Pinned Dependencies
12. ✅ Packaging
13. ✅ SAST
14. ✅ Security Policy
15. ✅ Signed Releases
16. ✅ Token Permissions
17. ✅ Vulnerabilities
18. ✅ Webhooks

**Monitoring:**
- Weekly automated scans
- PR validation for main branch
- Trend analysis
- Public scorecard badge

### SBOM & Attestation

**Standards:**
- SPDX 2.3 (ISO/IEC 5962:2021)
- CycloneDX 1.5
- VEX for vulnerability exploitability

**Signing:**
- Sigstore (keyless)
- Cosign for artifacts
- Rekor transparency log
- GitHub Attestations API

**Usage:**
```bash
# Generate SBOM
syft packages dir:. -o spdx-json=sbom.json

# Sign SBOM
cosign sign-blob --yes sbom.json \
  --output-signature sbom.json.sig \
  --output-certificate sbom.json.cert

# Verify signature
cosign verify-blob sbom.json \
  --signature sbom.json.sig \
  --certificate sbom.json.cert
```

## Vulnerability Management

### Severity Classification

| Severity | CVSS Score | Response Time | Action |
|----------|-----------|---------------|--------|
| Critical | 9.0-10.0 | 24 hours | Immediate fix |
| High | 7.0-8.9 | 7 days | Prioritized fix |
| Medium | 4.0-6.9 | 30 days | Scheduled fix |
| Low | 0.1-3.9 | 90 days | Track and plan |

### Remediation Process

1. **Detection**: Automated scanning identifies vulnerability
2. **Triage**: Security team assesses impact and exploitability
3. **Assignment**: Ticket created and assigned
4. **Fix**: Patch developed and tested
5. **Deployment**: Emergency deployment if critical
6. **Verification**: Rescan to confirm fix
7. **Documentation**: Update security advisories

### Exception Process

**When exceptions are allowed:**
- False positive confirmed
- Vulnerability not exploitable in context
- Mitigation controls in place
- Vendor fix not available

**Exception requirements:**
- Written justification
- Risk assessment
- Compensating controls
- Review by security team
- Expiration date (max 90 days)
- Documentation in VEX

## Security Gates

### PR Quality Gates

All PRs must pass:

1. ✅ **Secret Scanning**: No exposed secrets
2. ✅ **SAST**: No critical findings
3. ✅ **Dependency Scan**: No critical CVEs
4. ✅ **License Compliance**: No prohibited licenses
5. ✅ **SBOM**: Generated and signed
6. ✅ **Policy Enforcement**: OPA policies pass
7. ✅ **Code Coverage**: ≥98%
8. ✅ **Mutation Testing**: ≥90% kill rate

### Merge Requirements

**Branch Protection (main):**
- Require PR reviews (2+)
- Require status checks to pass
- Require signed commits (recommended)
- No force pushes
- No deletions
- CODEOWNERS review required

**Required Status Checks:**
- Aggregate coverage & enforce guardrail
- Mutation Testing Gate (90% kill rate)
- Security Scan
- OSSF Scorecard
- SBOM Generation
- License Compliance
- Policy Enforcement

### Release Gates

**Additional checks for releases:**
- Full security audit
- Performance benchmarks
- Integration tests pass
- E2E tests pass
- Documentation updated
- Change log prepared
- Release notes reviewed
- Artifacts signed
- SBOM published

## Incident Response

### Security Incident Classification

**P0 - Critical:**
- Active exploitation
- Data breach
- Service compromise
- Response: Immediate

**P1 - High:**
- Critical vulnerability discovered
- Potential for exploitation
- Compliance violation
- Response: Within 24 hours

**P2 - Medium:**
- Non-critical vulnerability
- Security misconfiguration
- Policy violation
- Response: Within 7 days

**P3 - Low:**
- Security advisory
- Best practice deviation
- Non-urgent fix
- Response: Next sprint

### Response Workflow

1. **Detection & Reporting**
   - Automated alerts
   - User reports
   - Researcher disclosure

2. **Initial Assessment**
   - Severity classification
   - Impact analysis
   - Affected versions

3. **Containment**
   - Disable vulnerable features
   - Block attack vectors
   - Isolate affected systems

4. **Remediation**
   - Develop fix
   - Security review
   - Testing

5. **Deployment**
   - Emergency release if critical
   - Staged rollout
   - Monitoring

6. **Communication**
   - Security advisory
   - User notification
   - CVE publication (if applicable)

7. **Post-Mortem**
   - Root cause analysis
   - Process improvements
   - Training updates

## Best Practices

### Secure Development

1. **Input Validation**
   - Validate all inputs
   - Use allowlists, not blocklists
   - Type checking with mypy

2. **Authentication & Authorization**
   - Use proven libraries
   - Multi-factor authentication
   - Least privilege principle

3. **Cryptography**
   - Use secrets module for tokens
   - Modern algorithms (AES-256, RSA-2048+)
   - Proper key management

4. **Error Handling**
   - Fail securely
   - No sensitive data in errors
   - Comprehensive logging

5. **Third-Party Code**
   - Vet dependencies
   - Pin versions
   - Regular updates
   - SBOM tracking

### Security Testing

1. **Unit Tests**
   - Test security functions
   - Edge cases and boundaries
   - Error conditions

2. **Integration Tests**
   - Authentication flows
   - Authorization checks
   - Data validation

3. **Security Tests**
   - Penetration testing (annual)
   - Fuzz testing
   - Threat modeling

## Compliance & Standards

### Regulatory Compliance
- SEC (Securities and Exchange Commission)
- FINRA (Financial Industry Regulatory Authority)
- GDPR (General Data Protection Regulation)
- SOC 2 Type II
- ISO 27001

### Security Standards
- OWASP Top 10
- CWE Top 25
- NIST SSDF
- SLSA Level 3
- OSSF Best Practices

### Development Standards
- SPDX 2.3
- CycloneDX 1.5
- SARIF 2.1.0
- OpenAPI 3.0

## Tools & Resources

### Security Tools
- **SAST**: Bandit, Semgrep, CodeQL
- **Secret Scanning**: Gitleaks, TruffleHog, detect-secrets
- **Dependency**: Safety, pip-audit, Grype, Trivy
- **Container**: Trivy, Grype, Syft
- **SBOM**: Syft, CycloneDX
- **Signing**: Sigstore, Cosign
- **Policy**: Open Policy Agent (OPA)

### Resources
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [NIST SSDF](https://csrc.nist.gov/Projects/ssdf)
- [SLSA Framework](https://slsa.dev/)
- [OSSF Best Practices](https://bestpractices.coreinfrastructure.org/)
- [CWE](https://cwe.mitre.org/)
- [GitHub Security Lab](https://securitylab.github.com/)

### Internal Documentation
- [Main Security Policy](../SECURITY.md)
- [PR Testing Guide](PR_TESTING_GUIDE.md)
- [Contributing Guidelines](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)

## Contact

**Security Team**: security@geosync.local
**Bug Bounty**: [GitHub Security Advisory](https://github.com/neuron7xLab/GeoSync/security/advisories/new)
**General Questions**: Open an issue with `security` label

---

**Last Updated**: 2025-11-11
**Version**: 1.0
**Review Frequency**: Quarterly
**Next Review**: 2026-02-11
