# Security Policy for TradePulse-QLW

## Overview

This document outlines security measures and best practices for TradePulse-QLW v1.1.0.

## Security Features

### API Layer

1. **Rate Limiting**
   - 20 requests per second per IP address
   - Implemented via SlowAPI middleware
   - Prevents DoS attacks

2. **Payload Size Guard**
   - Maximum request size: 4MB
   - Protects against memory exhaustion
   - Returns 413 Payload Too Large

3. **Structured Audit**
   - SHA256 hash of request body
   - Timestamp tracking
   - IP address logging (anonymized in production)
   - Audit headers: `X-Audit-TS`, `X-Audit-Req`

4. **PII Masking**
   - Sensitive payloads hashed in logs
   - No plaintext credentials or tokens
   - Configurable mask filter

### Container Security

1. **Pod Security Standards (PSS)**
   - Level: Restricted
   - No privilege escalation
   - Non-root user (UID 1000)
   - Read-only root filesystem
   - Drop all capabilities

2. **Security Context**
   ```yaml
   securityContext:
     runAsNonRoot: true
     runAsUser: 1000
     fsGroup: 2000
     readOnlyRootFilesystem: true
     allowPrivilegeEscalation: false
     capabilities:
       drop: ["ALL"]
   ```

3. **Network Policies**
   - Ingress: Only from allowed namespaces
   - Egress: Restricted to required services
   - No unrestricted outbound

### Secrets Management

1. **Kubernetes Secrets**
   - Never hardcode credentials
   - Use `envFrom` with secretRef
   - Rotate secrets regularly

2. **TLS/mTLS**
   - Enforce HTTPS for external endpoints
   - mTLS for service-to-service
   - Cert-manager for rotation

### Supply Chain

1. **Dependency Pinning**
   - Exact versions in pyproject.toml
   - Lock files for reproducibility
   - Regular security audits

2. **Image Scanning**
   - Grype/Syft for vulnerability scanning
   - SBOM generation
   - Provenance attestation

3. **CI/CD Pipeline**
   - Signed commits required
   - Code review mandatory
   - Automated security checks

## Vulnerability Reporting

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Email security contact: security@tradepulse.example (adjust for your org)
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Impact assessment
   - Suggested fix (if any)

We will respond within 48 hours and work on a fix.

## Security Checklist for Operators

### Before Deployment

- [ ] Review all configuration files for sensitive data
- [ ] Ensure TLS certificates are valid and rotated
- [ ] Verify network policies are in place
- [ ] Check RBAC permissions are minimal
- [ ] Audit logging is enabled
- [ ] Secrets are stored in Kubernetes/Vault, not config

### Runtime Monitoring

- [ ] Monitor audit logs for anomalies
- [ ] Track rate limit violations
- [ ] Alert on suspicious patterns
- [ ] Review Prometheus metrics for abuse
- [ ] Check for CVEs in dependencies monthly

### Incident Response

1. **Detection**: Monitor alerts from Prometheus/Grafana
2. **Containment**: Use PDB to maintain availability during rollback
3. **Eradication**: Roll back to known-good version via Argo
4. **Recovery**: Verify all systems operational
5. **Lessons Learned**: Update runbooks

## Compliance

TradePulse-QLW follows:
- OWASP Top 10 mitigations
- CIS Kubernetes Benchmark
- NIST Cybersecurity Framework
- SOC 2 Type II controls (when applicable)

## Audit Trail

All API requests generate:
- Timestamp (ms precision)
- Request hash (SHA256)
- Source IP (anonymized in prod)
- Response status

Audit logs retained for 7 years (configurable).

## Updates and Patches

Security patches are released:
- Critical: Within 24 hours
- High: Within 7 days
- Medium: Within 30 days
- Low: In next scheduled release

Subscribe to security advisories at [your repo]/security/advisories.

## Cryptography

1. **Hash Functions**: SHA256 for audit
2. **TLS**: TLS 1.3 minimum
3. **Key Storage**: External KMS or Vault
4. **No custom crypto**: Use standard libraries

## Questions?

For security questions, contact: security@tradepulse.example

Last updated: 2025-11-12
