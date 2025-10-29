# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

### Responsible Disclosure Policy

We strongly encourage responsible disclosure and commit to working with researchers to promptly address reported issues.

- **Primary contact**: `security@tradepulse.local`
- **Backup contact**: Direct message the maintainers via the [GitHub Security Advisory](https://github.com/neuron7x/TradePulse/security/advisories/new) form.
- **SLA overview**:
  - Acknowledge receipt within **48 hours**.
  - Provide an initial assessment within **5 business days**.
  - Deliver fix timelines based on severity (see below) and share remediation status updates at least every **5 business days** until resolution.
- **Safe harbor**: Good-faith security research that complies with this policy will not be subject to legal action or revocation of access.

### Disclosure Process

1. **Report**: Send details to **security@tradepulse.local** or via [GitHub Security Advisories](https://github.com/neuron7x/TradePulse/security/advisories/new)
   - Include description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
   - Proof of concept (if available)
   - Your contact information

2. **Acknowledgment**: We will acknowledge receipt within 48 hours

3. **Investigation**: We will investigate and provide updates every 5 business days
   - Initial triage: 24-48 hours
   - Impact assessment: 3-5 business days
   - Regular status updates

4. **Resolution**: 
   - Critical vulnerabilities: Fixed within 7 days
   - High severity: Fixed within 30 days
   - Medium/Low severity: Fixed within 90 days
   - You will be credited in release notes (unless you prefer to remain anonymous)

5. **Disclosure**: After a fix is released, we will publish a security advisory
   - CVE assignment if applicable
   - Public disclosure 7 days after patch release
   - Coordinated with reporter

### Severity Classification

| Severity | Description | Response Time |
|----------|-------------|---------------|
| Critical | Remote code execution, authentication bypass | 7 days |
| High | Data exposure, privilege escalation | 30 days |
| Medium | DoS, information disclosure | 90 days |
| Low | Minor issues with minimal impact | 180 days |

### What to Report

We're interested in any type of security issue, including:
- Authentication/authorization bypasses
- Data exposure or leakage
- Injection vulnerabilities (SQL, command, code injection)
- Cross-site scripting (XSS) in web interfaces
- Denial of service vulnerabilities
- Cryptographic issues
- Dependency vulnerabilities with known exploits
- API security issues
- Secrets or credentials in code
- Insecure defaults or configurations

### What NOT to Report

The following are **not** considered security vulnerabilities:
- Vulnerabilities in dependencies without a proof of exploit
- Missing security headers without demonstrated impact
- Issues requiring physical access
- Social engineering attacks
- Missing best practices without security impact
- Issues in deprecated or EOL dependencies

### Bug Bounty Program

We currently do not offer monetary rewards for security findings. However, we recognize and credit all valid security reports publicly (with permission).

### Hall of Fame

We maintain a [Security Hall of Fame](SECURITY_HALL_OF_FAME.md) recognizing security researchers who have responsibly disclosed vulnerabilities.

---

## Security Best Practices

### For Contributors

#### 1. Secrets Management

**Never commit secrets to the repository:**
- API keys
- Passwords
- Private keys
- Connection strings
- Tokens

**Use environment variables:**
```bash
# Good
export TRADING_API_KEY="your-key-here"

# Bad (never do this)
api_key = "sk-12345..."  # in code
```

**Check for secrets before committing:**
```bash
# Use git-secrets or similar tools
git secrets --scan
```

Run `gitleaks detect --redact --source .` before every push (the same command executes in CI). If anything leaks, revoke the credential, re-issue fresh ones with `python -m scripts.cli secrets-issue-dynamic` (or the appropriate cloud secret rotation workflow), and record the incident in both `SECURITY.md` (rotation log) and the 🔐 Security section of the changelog.

#### 2. Input Validation

**Always validate and sanitize inputs:**
```python
# Good
def process_price(price: float) -> float:
    if not isinstance(price, (int, float)):
        raise ValueError("Price must be numeric")
    if price <= 0:
        raise ValueError("Price must be positive")
    return float(price)

# Bad
def process_price(price):
    return float(price)  # No validation
```

#### 3. Dependency Management

**Keep dependencies up to date:**
```bash
# Regular updates
pip install -U -r requirements.lock

# Check for known vulnerabilities

```bash
make security-audit
```

The helper script wraps `pip-audit` with consistent flags, emits a human-readable summary,
and optionally writes a JSON report (see `python scripts/dependency_audit.py --help`). Use
`--include-dev` to cover development tooling as well.

**Supply-chain guardrails:**

```bash
make sbom
make supply-chain-verify
```

- `make sbom` materializes a CycloneDX 1.5 SBOM covering runtime and development dependencies.
- `make supply-chain-verify` enforces pinning requirements, cross-checks the deny list defined in
  `configs/security/denylist.yaml`, and writes a transparency report to
  `reports/supply_chain/dependency-verification.json`.

#### Encryption & Key Management

- **In transit**: Terminate all external-facing services with **TLS 1.3** using modern cipher
  suites (e.g., `TLS_AES_256_GCM_SHA384`). Redirect plaintext HTTP traffic to HTTPS and enable
  HSTS.
- **At rest**: Encrypt storage volumes, S3 buckets, databases, and message queues with
  **AES-256** or stronger. Confirm that managed services (RDS, S3, EBS, etc.) have encryption
  toggled on by default.
- **Key management**: Store encryption keys in a dedicated KMS or HSM (e.g., AWS KMS, Vault).
  Enforce automated key rotation at least annually, grant least-privilege access to keys, and
  audit key usage via centralized logging.

#### Automated Security Scanning

- **Infrastructure as Code (IaC)**: Integrate tools such as `terraform validate`, `checkov`, or
  `tfsec` into CI to evaluate Terraform/CloudFormation manifests on every merge request.
- **Container image scanning**: Scan images during build and before deployment with
  `trivy`/`grype`, and block promotion when high/critical findings exist.
- **Continuous monitoring**: Schedule nightly scans of production registries and IaC sources to
  detect drift or newly disclosed CVEs.

#### Dynamic Testing & Penetration Testing

- **DAST**: Run authenticated dynamic scans (e.g., OWASP ZAP) against staging environments as
  part of the release pipeline. Ensure scans cover core APIs, web UI, and critical workflows.
- **Penetration testing**: Commission manual testing for every major release or at least twice
  per year. Scope should include application, APIs, and supporting infrastructure.
- **Remediation SLAs**: Resolve critical findings within **7 days**, high severity within
  **30 days**, and medium severity within **90 days**. Track remediation status in the security
  backlog and verify fixes with re-tests.

#### Centralized Logging, Monitoring, and Response

- **SIEM/SOAR**: Forward application, infrastructure, authentication, and audit logs to the
  central SIEM (e.g., Splunk, ELK, Sentinel) with retention policies that meet compliance needs.
- **Alerting**: Define alert rules for authentication anomalies, privileged changes, network
  anomalies, and critical application errors. Route alerts to the on-call rotation with clear
  severity classifications.
- **Response playbooks**: Maintain SOAR automation and manual runbooks for credential compromise,
  suspicious deployments, data exfiltration, and availability incidents. Review and exercise
  playbooks quarterly.

#### Backup & Disaster Recovery

- **Backups**: Automate encrypted (AES-256) backups for databases, configuration stores, and
  object storage. Store backups in separate accounts/regions with immutable retention policies.
- **RPO/RTO targets**: Document Recovery Point Objective (**RPO**) and Recovery Time Objective
  (**RTO**) for each tiered service (e.g., Tier 0: RPO ≤ 15 min, RTO ≤ 1 hr) and align backup
  frequency accordingly.
- **Testing**: Perform disaster recovery tests at least annually, validating restore procedures,
  failover automation, and communication plans. Capture lessons learned and update runbooks.

```bash
# Direct invocation if you prefer to call pip-audit yourself
pip-audit -c constraints/security.txt -r requirements.txt --no-deps

# Or use safety as a secondary check
safety check
```

**Review dependency changes:**
- Check changelogs before updating
- Test thoroughly after updates
- Pin versions in production

**CycloneDX SBOM generation:**
- Every push, pull request, and release automatically generates validated CycloneDX SBOMs (JSON and XML).
- Download SBOM artifacts from the `CycloneDX SBOM` workflow run or from the published release assets.
- Use these SBOMs to audit dependency inventories and share with stakeholders.

**Container signing & provenance:**
- Release container images are pushed to GHCR with keyless [Sigstore Cosign](https://github.com/sigstore/cosign) signatures attached to the digest.
- Every release produces a SLSA v3 provenance statement for the container image via the official [slsa-github-generator](https://github.com/slsa-framework/slsa-github-generator).
- Consumers can verify signatures with `cosign verify ghcr.io/<owner>/<repo>@<digest>` and download provenance attestations directly from GHCR.

#### 4. Web Interface Hardening

- Enforce strict Content Security Policy headers via `apps/web/next.config.js`. Frame embedding is blocked and only same-origin resources are allowed by default.
- Run `npm run security:audit-scripts` inside `apps/web` before shipping UI changes. The audit fails if unchecked third-party script URLs are introduced.
- Avoid inline scripts; prefer vetted modules bundled at build time. When inline styles are required, keep them minimal and scoped.
- Document any intentional CSP relaxations directly in the pull request and in `SECURITY.md`.

#### CSRF and clickjacking test harness

- The Playwright-based UI security suite asserts that all state-changing requests include valid CSRF tokens and that invalid tokens are rejected with HTTP 403 responses. The same suite verifies preflight requests and SameSite cookie attributes.
- Clickjacking regression checks ensure that the `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'` headers are present on protected routes. Results are published as part of the `tests.yml` workflow and any regression blocks merges.
- Any route that intentionally permits embedding must be documented with an allowlist and accompanied by compensating controls (e.g., signed iframe tokens).

#### CSP reporting

- CSP violation reports are collected at `/api/security/csp-report` and forwarded to the security data lake for triage. Dashboards in Grafana highlight spikes per origin and script hash to catch injection attempts.
- PRs that change CSP headers must include updated detection rules and dashboard alerts. The security team triages new CSP report signatures within 24 hours.

#### TLS baseline

- All public endpoints terminate TLS at the edge with **minimum TLS 1.2** support; TLS 1.3 is preferred and enabled wherever client support allows.
- Cipher suites follow Mozilla's "modern" profile: `TLS_AES_256_GCM_SHA384`, `TLS_AES_128_GCM_SHA256`, and `TLS_CHACHA20_POLY1305_SHA256`. Legacy RSA suites are disabled.
- Automated TLS scans run weekly (`security.yml` schedule) using `sslyze` to detect regressions. Any downgrade fails the pipeline and pages the on-call engineer.

#### 5. Code Review

**Security checklist for PRs:**
- [ ] No hardcoded secrets
- [ ] Input validation on all external data
- [ ] Proper error handling (no sensitive data in errors)
- [ ] Authentication/authorization checks
- [ ] SQL queries use parameterization
- [ ] File operations validate paths
- [ ] External commands properly escaped

---

## Security Tooling

### Automated Security Scanning

We use multiple tools in CI/CD:

#### 1. CodeQL (GitHub Advanced Security)
```yaml
# Automatically scans code for vulnerabilities
# Configured in .github/workflows/codeql.yml
```

#### 2. Bandit (Python Security Linter)
```bash
# Run locally
bandit -r core/ backtest/ execution/ interfaces/

# Common issues detected:
# - Use of assert in production
# - Hardcoded passwords
# - SQL injection risks
# - Shell injection risks
```

#### 3. Safety (Dependency Checker)
```bash
# Check for known vulnerabilities
safety check --json

# Update requirements
safety check --update
```

#### 4. pip-audit
```bash
# Audit Python packages
pip-audit --desc --format json
```

#### 5. Semgrep (Static Analysis)
```bash
# Run semantic code analysis
semgrep --config=auto .
```

#### 6. Container vulnerability scanning

Container images built from the root `Dockerfile` are scanned on every push, pull request, and weekly schedule. The `Security Scan` workflow builds a fresh image and executes Trivy and Grype against it. The pipeline fails immediately if any **critical** vulnerabilities are found (high severity findings are surfaced in SARIF reports but do not gate merges). Reports are uploaded to the repository's Security tab for triage and tracking.

#### 7. TLS regression scanning
```bash
# Validate edge TLS posture
poetry run sslyze edge.tradepulse.local --regular
```
The scheduled job exits non-zero if protocols below TLS 1.2 or non-approved cipher suites are presented.

### Pre-commit Hooks

Install security checks as pre-commit hooks:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# .pre-commit-config.yaml should include:
# - bandit
# - detect-secrets
# - check-added-large-files
```

---

## Common Security Patterns

### 1. API Key Management

**Development:**
```bash
# .env (never commit this file)
EXCHANGE_API_KEY=your-key
EXCHANGE_API_SECRET=your-secret
```

**Production:**
- Use environment variables
- Use secrets management (AWS Secrets Manager, HashiCorp Vault)
- Rotate keys regularly

#### Vault-backed secrets workflows

- **Mount structure** – All runtime credentials are sourced from `secret/data/<service>/<env>` paths in HashiCorp Vault. Each service account has a scoped Vault role with narrowly defined policies that only allow reading its own path.
- **Dynamic secrets** – Database and messaging credentials are provisioned via Vault database engines with 55-minute TTLs and automatic revocation on lease expiry. Application deployments request fresh leases during startup and refresh them every 45 minutes.
- **Automation tooling** – The `python -m scripts.cli secrets-issue-dynamic` command wraps the Vault API using the
  `application.secrets.hashicorp.DynamicCredentialManager` to fetch, renew, and persist short-lived credentials with full audit
  coverage. Cron jobs invoke it for pre-flight rotations.
- **Secret injection** – CI/CD pipelines authenticate to Vault using GitHub OIDC and render secrets into ephemeral environment variables. Long-lived static `.env` files are forbidden in production.

#### Key rotation playbook

1. **Registration** – Every secret stored in Vault is catalogued with owner, environment, rotation cadence, and fallback contact in the infrastructure configuration repository.
2. **Automation** – A nightly GitHub Actions workflow verifies that no credential exceeds its max TTL. The workflow triggers Vault rotation APIs for any secret older than its policy window and files a ticket with the owning team.
3. **Graceful reloads** – Services subscribe to secret update events via the secrets-rotator sidecar pattern. On rotation, the sidecar refreshes in-memory credentials, updates connection pools, and confirms healthy status to Vault.
4. **Break-glass overrides** – Emergency tokens are generated with 1-hour TTLs, require dual approval in the PAM system, and are logged with justification.

#### Secrets audit logging

- Vault audit devices forward JSON logs to the centralized SIEM (`observability/audit-stream`). Logs capture token IDs, accessor, requesting service, path, and IP metadata.
- Audit logs are retained for 400 days and analysed with anomaly detection rules (e.g., out-of-hours access, secrets enumeration attempts).
- Weekly compliance reports enumerate rotation status, stale leases, and privileged access outliers. Findings trigger mandatory post-mortems for unresolved anomalies beyond 7 days.
- Application services leverage the in-process `SecretManager` to emit signed audit records (via `src.audit.AuditLogger`) for every `get`, provider resolution, and forced refresh. Each entry records the secret metadata (never the value), caller identity, source IP, operation status, and is delivered to the configured webhook/SIEM sinks.

### 2. Database Queries

**Use parameterized queries:**
```python
# Good
cursor.execute("SELECT * FROM trades WHERE symbol = ?", (symbol,))

# Bad
cursor.execute(f"SELECT * FROM trades WHERE symbol = '{symbol}'")
```

### 3. File Operations

**Validate file paths:**
```python
import os

def read_config(filename: str) -> dict:
    # Prevent path traversal
    base_dir = "/app/configs"
    full_path = os.path.normpath(os.path.join(base_dir, filename))
    
    if not full_path.startswith(base_dir):
        raise ValueError("Invalid file path")
    
    with open(full_path, 'r') as f:
        return json.load(f)
```

### 4. Error Handling

**Don't expose sensitive information:**
```python
# Good
try:
    result = execute_trade(order)
except Exception as e:
    logger.error(f"Trade execution failed: {type(e).__name__}")
    return {"error": "Trade execution failed"}

# Bad
except Exception as e:
    return {"error": str(e)}  # May expose database structure, API keys, etc.
```

---

## Security Checklist for Releases

Before releasing a new version:

- [ ] Run all security scanners (bandit, safety, semgrep)
- [ ] Update all dependencies to latest secure versions
- [ ] Review and rotate any compromised credentials
- [ ] Check for hardcoded secrets in codebase
- [ ] Verify authentication/authorization logic
- [ ] Review recent security advisories for dependencies
- [ ] Update CHANGELOG.md with security fixes
- [ ] Create security advisory if needed

---

## Threat Model

### Assets
- Trading strategies and algorithms
- Market data and analytics
- API credentials and secrets
- User funds and positions
- System availability

### Threats
- **Unauthorized Access**: Compromise of API keys or credentials
- **Data Manipulation**: Tampering with market data or orders
- **Information Disclosure**: Leakage of trading strategies
- **Denial of Service**: System unavailability during critical trading
- **Supply Chain**: Compromised dependencies

### Mitigations
- Environment-based secrets management
- Input validation and sanitization
- Encrypted communications (TLS/SSL)
- Rate limiting and monitoring
- Regular security audits
- Dependency scanning

## Контроль required status checks

- Coverage check (Codecov) має бути обов'язковим для PR у main/develop.
- Якщо coverage check зник, додайте його у Branch protection rules.
- Як це зробити: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches

**Coverage інтеграція:**  
- [Codecov + GitHub інтеграція](https://docs.codecov.com/docs/github-checks)

---

## Incident Response

In case of a security incident:

1. **Contain**: Isolate affected systems
2. **Assess**: Determine scope and impact
3. **Notify**: Contact security@tradepulse.local
4. **Remediate**: Apply fixes and patches
5. **Review**: Post-mortem and lessons learned
6. **Disclose**: Responsible disclosure to users

---

## References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security.html)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)

---

## Contact

- **Security Issues**: security@tradepulse.local
- **General Issues**: [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)

---

**Last Updated**: 2025-01-01
