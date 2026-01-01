# Summary
- [ ] Explain the purpose of this change and the primary outcomes.
- [ ] Link related issues, follow-up tasks, or design docs.
- [ ] Indicate if this PR contains **breaking changes**

## Central File Justification
<!-- Required if touching core/params.py, bridge.py, or neural_params.yaml -->

## Change Type
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Performance improvement
- [ ] Documentation update
- [ ] Security enhancement
- [ ] Refactoring (no functional changes)
- [ ] Infrastructure/CI/CD changes

# Testing
## Automated Tests
- [ ] `pytest` (unit, integration, property, fuzz, contracts, security)
- [ ] Data quality gates (`pytest tests/data` or `python scripts/data_sanity.py ...`)
- [ ] Contract compatibility (`pytest tests/contracts`)
- [ ] Security scans (Bandit, secret-leak detection, CodeQL, Semgrep)
- [ ] UI smoke & accessibility (Playwright + aXe)
- [ ] Performance benchmarks (no regressions >10%)
- [ ] Mutation testing (90%+ kill rate)

## Manual Testing
- [ ] Tested locally with sample data
- [ ] Tested edge cases and error scenarios
- [ ] Verified backward compatibility (if applicable)

# Quality Checklist
## Code Quality
- [ ] Code follows project style guidelines (pre-commit hooks pass)
- [ ] No hardcoded secrets or credentials
- [ ] Error handling is comprehensive
- [ ] Logging is appropriate and secure
- [ ] Comments added for complex logic

## Security
- [ ] No SQL injection vulnerabilities
- [ ] No command injection vulnerabilities (no shell=True)
- [ ] Input validation implemented
- [ ] Authentication/authorization checked (if applicable)
- [ ] Dependencies are pinned and scanned for vulnerabilities
- [ ] No use of eval(), pickle.loads() without validation
- [ ] Security policies (OPA) pass

## Performance
- [ ] No performance regressions (benchmarks pass)
- [ ] Memory usage is acceptable
- [ ] Database queries are optimized (if applicable)
- [ ] Caching implemented where appropriate

## Compliance & Standards
- [ ] License compliance checked (no GPL-3.0, AGPL-3.0)
- [ ] SBOM generated and signed
- [ ] Code coverage ≥98%
- [ ] Cyclomatic complexity acceptable (<10 avg, <15 max)
- [ ] PR size is reasonable (<500 lines preferred)

## Documentation
- [ ] Documentation updated or confirmed not required
- [ ] API changes documented (if applicable)
- [ ] README updated (if applicable)
- [ ] Migration guide provided (for breaking changes)

## Infrastructure & CI/CD
- [ ] Workflow changes follow security best practices
- [ ] Actions are pinned to SHA (not tags)
- [ ] Minimal permissions specified
- [ ] OIDC used instead of long-lived credentials (if applicable)

## Review & Deployment
- [ ] CODEOWNERS for touched areas acknowledged
- [ ] Telemetry/metrics reviewed or updated
- [ ] Security, performance, and backward compatibility risks evaluated
- [ ] Rollback plan prepared (for high-risk changes)
- [ ] Deployment runbook updated (if needed)

# Additional Context
<!-- Add any other context about the PR here, including:
- Screenshots/recordings for UI changes
- Performance benchmark results
- Security considerations
- Migration notes
-->

---

**Automated Quality Gates:**
The following will be automatically checked:
- ✅ Code coverage ≥98%
- ✅ Mutation kill rate ≥90%
- ✅ No critical security vulnerabilities
- ✅ License compliance
- ✅ SBOM generation and signing
- ✅ SLSA provenance attestation
- ✅ Performance regression analysis
- ✅ Complexity analysis
- ✅ Security policy enforcement (OPA)
- ✅ Dependency review
- ✅ OSSF Scorecard evaluation
