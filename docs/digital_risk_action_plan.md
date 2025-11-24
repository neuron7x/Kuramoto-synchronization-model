# Digital Risk Action Plan

This playbook operationalizes confidentiality, integrity, availability, authentication/authorization hardening, and legal/ethical safeguards for TradePulse. It is structured for rapid execution and continuous coverage across technical, organizational, human, and legal layers.

## 0. First 72 Hours (Stabilize & Contain)
- Enforce MFA for all admin and production-facing identities; disable dormant privileged accounts.
- Rotate long-lived tokens/API keys; shorten TTLs and revoke unused credentials.
- Close publicly exposed ports; require bastion access with mTLS for service-to-service and SSH.
- Enable/strengthen WAF and rate limiting on internet perimeters; activate CDN/DDoS protection.
- Set DMARC (`p=reject`), DKIM, SPF to strict modes for all corporate domains.
- Centralize logs into SIEM; page on suspicious auth, privilege changes, and anomalous traffic.
- Validate backups with a live restore drill for Tier-0/Tier-1 systems; document RPO/RTO.
- Scan repos for secrets; rotate anything discovered immediately.
- Run targeted DAST on critical external APIs and block release on critical/high findings.
- Issue a phishing and access-control refresher to all staff and contractors.

## 1. Confidentiality Controls
- **Data inventory & ownership:** Maintain a registry of sensitive data sets with owners, lawful basis, and allowed roles; recertify quarterly.
- **Access minimization:** Apply least privilege via RBAC/ABAC; enforce just-in-time elevation with automatic expiry and audit trails.
- **Encryption:** TLS 1.2+/1.3 with HSTS and modern ciphers; full-disk/database encryption with KMS/HSM-backed keys and automated rotation.
- **Secrets management:** Centralize secrets, ban inline secrets in code/CI logs, and implement mandatory pre-commit/CI secret scans.
- **Data loss prevention:** DLP policies for email/storage/USB; leak scanning on repositories and build artifacts; mask PII in logs by default.

## 2. Integrity Controls
- **Signed artifacts:** Require signing of containers, releases, and IaC manifests; verify signatures in CI/CD.
- **File/config integrity:** Enable file integrity monitoring on critical hosts; detect config drift and block unreviewed changes.
- **Immutable logging:** Append-only/WORM audit logs with clock synchronization; retain ≥7 years for regulated data.
- **Secure SDLC:** SAST/DAST/IAST, SBOM generation, license checks, and deny-list enforcement on dependencies. Mandate code review and protected branches with signed commits.

## 3. Availability Controls
- **Resilience:** Multi-AZ/region deployments with health checks, auto-scaling, and automated failover for Tier-0/Tier-1 services.
- **Backups & drills:** Encrypted backups with cross-region copies; quarterly restore drills tracked with success metrics.
- **Traffic protection:** Rate limiting, circuit breakers, queueing, and priority lanes for critical APIs; pre-defined degradation modes.
- **BCP/DRP:** Documented business continuity and disaster recovery plans, escalation matrix, and communication templates.

## 4. Authentication & Authorization Hardening
- **Identity:** Central IdP with SSO (SAML/OIDC) and SCIM lifecycle automation; automatic deprovisioning on termination or role change.
- **MFA & passwordless:** Enforce MFA everywhere; prefer FIDO2 for admins and production access.
- **Token hygiene:** Short TTL, audience-bound tokens; rotate keys regularly; restrict API keys by IP/context; require mutual TLS for service meshes.
- **Authorization:** Fine-grained RBAC/ABAC with JIT/JEA; log all privilege changes; periodic access recertification.

## 5. Attack Surface Reduction & Detection
- **Perimeter:** WAF+CDN with OWASP Top 10 rules, bot mitigation, geo/IP reputation filters, SYN/UDP flood protections.
- **Application security:** Strict CSP/security headers, runtime protection (RASP/WAAP) on critical APIs, fuzzing for parsers and external input handlers.
- **Phishing & social engineering:** Anti-spoofing controls (DMARC/DKIM/SPF), user awareness campaigns, and recurring phishing simulations.
- **Endpoint & network:** EDR/XDR coverage, network segmentation (zero trust), and minimized open ports. Admins use bastions or privileged access workstations.
- **Patch management:** SLA-driven remediation for critical/high CVEs; automated agent updates; CIS benchmark conformance checks.

## 6. Legal, Compliance, and Ethics
- **Framework alignment:** Map controls to GDPR/CCPA/ISO 27001/SOC 2/NIST 800-53; retain compliance evidence.
- **Vendor risk:** DPIA/DTIA for personal data, mandatory DPAs/SLAs, and sub-processor reviews with exit plans.
- **Policies & training:** Security/privacy/AUP policies with at least annual training and knowledge validation.
- **Incident readiness:** Legal review paths, evidence preservation, regulator/client notification templates, and counsel-on-call procedures.

## 7. Monitoring, Incident Response, and Metrics
- **SIEM/SOAR:** Centralize logs with correlation rules for auth anomalies, privilege changes, data exfiltration, and network anomalies; automate playbooks where safe.
- **Incident handling:** RACI, runbooks, escalation paths, and tabletop exercises at least twice per year; track MTTD/MTTR.
- **Metrics/KRIs:** MFA coverage, secret rotation latency, patch SLA adherence, % encrypted channels, backup restore success rate, and CSP violation trends.

## 8. Human Factors
- **Onboarding/offboarding:** Automated account provisioning/deprovisioning; temporary accounts expire automatically; contractors time-bound.
- **Secure workstations:** Enforced disk encryption, EDR, USB/media control, timely OS/browser patching, and least privilege locally.
- **Awareness:** Quarterly training on phishing, data handling, and incident reporting; signed acknowledgment of policies.

## 9. Risk Register Maintenance
- Maintain a digital risk register with owner, likelihood, impact, mitigation, and due dates.
- Update after every major architecture change or incident; review in quarterly risk councils.
- Tie critical risks to runbooks and monitoring rules to ensure detection and response coverage.
