---
owner: security@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Security Reports Guide — GeoSync

> How to read and respond to security reports in CI.

## Overview

CI generates security reports that identify vulnerabilities in:
1. **Source code** (SAST) — Bandit, CodeQL
2. **Dependencies** (SCA) — pip-audit, Safety  
3. **Container images** — Trivy, Grype
4. **Secrets** — detect-secrets, Gitleaks, TruffleHog

---

## Report Locations

| Type | Artifact | Format |
|------|----------|--------|
| SAST (Bandit) | `security-reports/bandit.json` | JSON |
| Dependency Scan | `dependency-reports/pip-audit-report.json` | JSON |
| Container Scan | `trivy-results.sarif`, `grype-results.sarif` | SARIF |
| Secret Scan | GitHub Security tab | SARIF |
| CodeQL | GitHub Security tab | SARIF |

---

## Reading Bandit (SAST) Reports

Bandit scans Python code for security issues.

### Severity Levels
- **HIGH** — Must fix before merge
- **MEDIUM** — Should fix, blocks if `--fail-on-severity MEDIUM`
- **LOW** — Informational, review and fix if practical

### Example Report
```json
{
  "filename": "core/auth/token.py",
  "issue_confidence": "HIGH",
  "issue_severity": "MEDIUM",
  "issue_text": "Possible hardcoded password: 'secret_key'",
  "line_number": 42,
  "test_id": "B105"
}
```

### Common Fixes

| Issue ID | Description | Fix |
|----------|-------------|-----|
| B105 | Hardcoded password | Use environment variables |
| B106 | Hardcoded password in function call | Use secrets manager |
| B110 | Try-except-pass | Add proper error handling |
| B303 | Use of insecure MD5/SHA1 hash | Use hashlib.sha256() |
| B608 | SQL injection | Use parameterized queries |

### Running Locally
```bash
# Full scan
bandit -r core backtest execution -ll

# Specific file
bandit -r core/auth/token.py -f json -o bandit-report.json
```

---

## Reading Dependency Reports (pip-audit)

pip-audit checks Python dependencies for known vulnerabilities.

### Example Report
```json
{
  "dependencies": [
    {
      "name": "requests",
      "version": "2.25.0",
      "vulns": [
        {
          "id": "GHSA-j8r2-6x86-q33q",
          "fix_versions": ["2.31.0"]
        }
      ]
    }
  ]
}
```

### Fixing Vulnerabilities

1. **Update the package**:
   ```bash
   # Update in requirements.txt to fixed version
   requests>=2.32.5
   ```

2. **Pin in security constraints** (`constraints/security.txt`):
   ```
   requests==2.32.5
   ```

3. **Regenerate lock files**:
   ```bash
   make lock
   ```

### Current Known Exceptions

The CI allows one known vulnerability as documented in `security.yml`:
- `GHSA-4xh5-x5gv-qwph` — pip itself, fixed in pip 25.3

---

## Reading Container Scan Reports (Trivy/Grype)

Container scans find vulnerabilities in base images and installed packages.

### SARIF Format
```json
{
  "runs": [{
    "results": [{
      "ruleId": "CVE-2024-12345",
      "level": "error",
      "message": {
        "text": "Package libexpat1 2.5.0 is affected by CVE-2024-12345"
      }
    }]
  }]
}
```

### Severity Mapping
- `CRITICAL` — **Blocks CI**, must fix
- `HIGH` — **Warning**, should fix soon
- `MEDIUM/LOW` — Informational

### Common Fixes

| Issue Type | Fix |
|------------|-----|
| Base image vuln | Update `FROM python:3.x-slim` to newer version |
| OS package vuln | Add `RUN apt-get update && apt-get upgrade -y` |
| Pip package vuln | Update in requirements.txt |

### Running Locally
```bash
# Build image
docker build -t geosync:scan .

# Scan with Trivy
trivy image geosync:scan --severity CRITICAL,HIGH

# Scan with Grype
grype geosync:scan --fail-on critical
```

---

## Reading CodeQL Reports

CodeQL finds security vulnerabilities through deep code analysis.

### Viewing Results
1. Go to **Security** tab in GitHub
2. Select **Code scanning alerts**
3. Filter by severity

### Common Alert Types

| Query | Description | Fix |
|-------|-------------|-----|
| py/sql-injection | SQL injection | Use parameterized queries |
| py/path-injection | Path traversal | Validate and sanitize paths |
| py/command-injection | Command injection | Avoid shell=True, use shlex |
| py/clear-text-logging | Sensitive data in logs | Mask or remove sensitive data |
| py/insecure-randomness | Weak randomness | Use secrets module |

---

## Secret Scanning

### detect-secrets Baseline
The project uses `.secrets.baseline` to track known false positives.

### If Secrets Found
1. **Don't push** secrets to the repository
2. **Rotate** any exposed credentials immediately
3. **Add to `.secrets.baseline`** only if false positive:
   ```bash
   detect-secrets scan --update .secrets.baseline
   git add .secrets.baseline
   ```

### True Positive Response
If a real secret is detected:
1. **Stop push immediately**
2. **Rotate the credential** in the source system
3. **Contact security team** if production secret
4. See `docs/runbook_secret_leak.md` for full procedure

---

## CI Security Workflow

### What Blocks Merge

| Check | Severity | Action |
|-------|----------|--------|
| Bandit | MEDIUM+ | Blocks |
| pip-audit | HIGH+ (non-exempt) | Blocks |
| Trivy/Grype | CRITICAL | Blocks |
| CodeQL | CRITICAL | Blocks |
| detect-secrets | Any new | Blocks |

### What Warns

| Check | Severity | Action |
|-------|----------|--------|
| Trivy/Grype | HIGH | Warning, uploaded to Security tab |
| CodeQL | HIGH | Warning, uploaded to Security tab |
| Bandit | LOW | Info only |

---

## False Positive Handling

### Bandit False Positives
```python
# nosec B101 - This assert is for type narrowing, not security
assert isinstance(value, str)  # nosec B101
```

### detect-secrets False Positives
1. Run: `detect-secrets scan --update .secrets.baseline`
2. Review: `detect-secrets audit .secrets.baseline`
3. Mark as false positive in audit

### pip-audit Exceptions
Add temporary exception in `security.yml` with:
- Comment explaining why
- Link to issue tracking fix
- Expiration date

---

## Quick Reference Commands

```bash
# Full security audit
make security-audit

# Bandit only
bandit -r core backtest execution -ll

# Dependency audit
python scripts/dependency_audit.py --requirement requirements.txt

# Secret scan
detect-secrets scan core backtest execution src application

# Container scan (after build)
docker build -t geosync:scan .
trivy image geosync:scan
```

---

## Escalation

| Severity | Response Time | Action |
|----------|---------------|--------|
| CRITICAL in prod deps | Immediate | Block all deploys, fix ASAP |
| HIGH in prod deps | 24 hours | Prioritize fix |
| CRITICAL in dev deps | 48 hours | Fix before next release |
| HIGH in dev deps | 1 week | Schedule fix |
| Container base image | 1 week | Update Dockerfile |

---

## Resources

- [OWASP Python Security](https://cheatsheetseries.owasp.org/cheatsheets/Python_Security_Cheat_Sheet.html)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [pip-audit Documentation](https://github.com/pypa/pip-audit)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [CodeQL Query Reference](https://codeql.github.com/codeql-query-help/python/)

---

*Last updated: 2025-12*
