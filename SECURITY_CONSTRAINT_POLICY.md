# Security Constraint Policy

## Overview

Ensures all security-critical packages are pinned to vetted versions free from known vulnerabilities.

## Fix Applied (2025-11-17)

**Problem**: `constraints/security.txt` covered only HTTP stack (5 packages), missing critical security packages.

**Solution**: Expanded to 16 packages:
- HTTP: certifi, requests, urllib3, idna, charset-normalizer
- Crypto/Auth: cryptography==46.0.3, PyJWT==2.10.1
- Templates: Jinja2==3.1.6, PyYAML==6.0.3
- Data/ORM: SQLAlchemy==2.0.44, pydantic==2.12.4, pandera==0.26.1
- System: configobj, setuptools, twisted

## Usage

Always use constraints with pip:

```bash
pip install -c constraints/security.txt -r requirements.txt
python scripts/verify_security_constraints.py
```

## Maintenance

- **Weekly**: Check for new CVEs
- **Monthly**: Update to latest stable versions
- **Immediate**: Fix critical vulnerabilities

### Update Process

1. Run `pip-audit -r requirements.txt`
2. Update `constraints/security.txt` with new versions
3. Test in isolated environment
4. Run `python scripts/verify_security_constraints.py`
5. Merge after CI passes

## Compliance

- NIST SP 800-53 (SC-18, SI-7)
- ISO 27001 (A.12.6.1)
- OWASP Top 10 (A06:2021)
- CIS Controls (7.1, 7.3)

## Verification

```bash
# Check constraints
python scripts/verify_security_constraints.py

# Auto-fix violations
python scripts/verify_security_constraints.py --fix
```

## Related Documentation

- [Security Framework](SECURITY_FRAMEWORK_SUMMARY.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Security Policy](SECURITY.md)
