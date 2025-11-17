# Security Constraint Policy

## Overview

This document defines the security constraint policy for TradePulse dependencies, ensuring that all security-critical packages are pinned to vetted versions that are free from known vulnerabilities.

## Critical Architecture Issue Fixed (2025-11-17)

**Issue**: The original `constraints/security.txt` was incomplete, covering only HTTP stack dependencies while missing critical security packages. This created a supply chain security vulnerability where CI/CD pipelines and production environments could install vulnerable versions of:
- `cryptography` (CVE-2023-50782, CVE-2024-26130, CVE-2024-0727)
- `PyYAML` (CVE-2020-14343 - arbitrary code execution)
- `Jinja2` (CVE-2024-34064 - XSS vulnerability)
- `PyJWT` (CVE-2022-29217 - key confusion attack)

**Impact**: Critical security vulnerability - production systems could run with known CVEs.

**Resolution**: Enhanced `constraints/security.txt` to include ALL security-critical packages with exact version pinning following Principal System Architect best practices 2025.

## Constraint File Purpose

The `constraints/security.txt` file serves as the **single source of truth** for security-critical package versions. It MUST be used in:
- All CI/CD workflows (GitHub Actions)
- All production deployments
- All development environments
- All testing environments

## Usage

### Installing Dependencies

Always use the `-c` flag with pip to enforce security constraints:

```bash
# Install production dependencies
pip install -c constraints/security.txt -r requirements.txt

# Install development dependencies
pip install -c constraints/security.txt -r requirements-dev.txt

# Install specific packages
pip install -c constraints/security.txt cryptography PyYAML
```

### CI/CD Integration

All GitHub Actions workflows MUST use the constraint file:

```yaml
- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -c constraints/security.txt -r requirements.txt
    pip install -c constraints/security.txt -r requirements-dev.txt
```

## Security-Critical Package Categories

### 1. HTTP Stack (Network Security)
- `certifi` - SSL/TLS certificate validation
- `urllib3` - HTTP client library
- `requests` - HTTP for humans
- `charset-normalizer` - Character encoding detection
- `idna` - Internationalized domain names

### 2. Cryptography & Authentication
- `cryptography` - Core cryptographic primitives
- `PyJWT` - JSON Web Token handling
- `PyJWT[crypto]` - JWT with cryptographic signing

### 3. Template & Serialization
- `Jinja2` - Template engine (XSS prevention)
- `PyYAML` - YAML parser (code execution prevention)

### 4. Data Validation & ORM
- `SQLAlchemy` - SQL database ORM (SQL injection prevention)
- `pydantic` - Data validation library
- `pydantic-settings` - Settings management
- `pandera` - DataFrame validation

### 5. System Packages
- `setuptools` - Package installation (path traversal fixes)
- `configobj` - Configuration parsing (ReDoS fixes)
- `twisted` - Event-driven networking (XSS fixes)

## Maintenance Process

### Regular Updates

Security constraints should be reviewed and updated:
- **Weekly**: Check for new CVEs in pinned packages
- **Monthly**: Update to latest stable versions after testing
- **Immediately**: Upon disclosure of critical vulnerabilities

### Update Workflow

1. **Monitor Security Advisories**
   ```bash
   # Run pip-audit to check for vulnerabilities
   pip-audit -r requirements.txt -r requirements-dev.txt
   ```

2. **Identify Required Updates**
   - Review CVE databases (NVD, GitHub Security Advisories)
   - Check package changelogs for security fixes
   - Validate fix availability in newer versions

3. **Test New Versions**
   ```bash
   # Create test environment
   python -m venv test_venv
   source test_venv/bin/activate
   
   # Test new constraint
   pip install -c constraints/security.txt.new package==new_version
   
   # Run security tests
   pytest tests/security/
   ```

4. **Update Constraint File**
   - Update version in `constraints/security.txt`
   - Document CVE fixes in comments
   - Update this policy document if needed

5. **Validate in CI**
   - Push to feature branch
   - Verify all CI workflows pass
   - Run full security scan

6. **Deploy**
   - Merge to main after review
   - Deploy to staging first
   - Monitor for issues before production

## Compliance & Auditing

### Security Standards

This policy ensures compliance with:
- **NIST SP 800-53**: SC-18 (Mobile Code), SI-7 (Software Integrity)
- **ISO 27001**: A.12.6.1 (Management of technical vulnerabilities)
- **CIS Controls**: 7.1 (Exploit Protection), 7.3 (Deploy Automated Patch Management)
- **OWASP Top 10**: A06:2021 (Vulnerable and Outdated Components)

### Audit Trail

All constraint updates are tracked via:
- Git commit history in `constraints/security.txt`
- CHANGELOG.md entries for security updates
- GitHub Security Advisory Database
- SBOM (Software Bill of Materials) generation

### Verification

To verify constraint enforcement:

```bash
# Check installed versions match constraints
./scripts/verify_security_constraints.py

# Run full security audit
bandit -r core backtest execution -f json -o security_report.json

# Generate SBOM
cyclonedx-py -r -o tradepulse-sbom.json
```

## Incident Response

If a vulnerability is discovered in a pinned package:

1. **Assess Severity** (CVSS score, exploitability)
2. **Immediate Action** (< 4 hours for critical)
   - Create hotfix branch
   - Update constraint file
   - Fast-track CI/CD pipeline
3. **Deploy** (follow progressive rollout)
4. **Verify** (confirm vulnerable version removed)
5. **Document** (post-mortem, lessons learned)

## Related Documentation

- [Security Framework](SECURITY_FRAMEWORK_SUMMARY.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Security Policy](SECURITY.md)
- [DevSecOps Integration](docs/security/devsecops/devsecops-integration-guide.md)

## Version History

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-11-17 | 1.0.0 | Principal System Architect | Initial policy, fixed critical constraint gap |

## References

- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security.html)
- [OWASP Dependency Check](https://owasp.org/www-project-dependency-check/)
- [NIST Software Supply Chain Security](https://www.nist.gov/itl/executive-order-improving-nations-cybersecurity/software-supply-chain-security-guidance)
- [CIS Software Supply Chain Security Guide](https://www.cisecurity.org/insights/white-papers/cis-software-supply-chain-security-guide)
