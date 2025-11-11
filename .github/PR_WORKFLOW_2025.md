# PR Workflow Architecture - 2025 Standards

> **Complete Pull Request Quality Assurance Pipeline**

## Workflow Orchestration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PR OPENED / UPDATED                             │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │  Parallel Execution      │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   SECURITY    │      │    QUALITY    │      │  PERFORMANCE  │
│   PIPELINE    │      │   PIPELINE    │      │   PIPELINE    │
└───────┬───────┘      └───────┬───────┘      └───────┬───────┘
        │                      │                        │
        │                      │                        │
   ┌────┴────┐            ┌────┴────┐            ┌────┴────┐
   │         │            │         │            │         │
   ▼         ▼            ▼         ▼            ▼         ▼

┌──────────────────────────────────────────────────────────────────────────┐
│                        SECURITY PIPELINE                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. Secret Scanning                        [security.yml]                │
│     ├─ Gitleaks (Git history)              ✓ Verified secrets           │
│     ├─ TruffleHog (verified)               ✓ Historical scan            │
│     └─ detect-secrets (baseline)           ✓ Pattern matching           │
│                                                                           │
│  2. SAST Analysis                          [security.yml, semgrep.yml]   │
│     ├─ Bandit (Python)                     ✓ 150+ security checks       │
│     ├─ Semgrep (Multi-lang)                ✓ OWASP Top 10               │
│     └─ CodeQL (Semantic)                   ✓ CWE Top 25                 │
│                                                                           │
│  3. Dependency Scanning                    [security.yml]                │
│     ├─ Safety (PyPA)                       ✓ Known vulnerabilities      │
│     ├─ pip-audit (OSV)                     ✓ Advisory database          │
│     └─ Exception handling                  ✓ Documented exclusions      │
│                                                                           │
│  4. Container Scanning                     [security.yml]                │
│     ├─ Trivy (critical CVEs)               ✓ Base image scan            │
│     ├─ Grype (multi-source)                ✓ Application deps           │
│     └─ SARIF upload                        ✓ GitHub Security tab        │
│                                                                           │
│  5. Policy Enforcement                     [security-policy-enforcement] │
│     ├─ OPA - Secrets                       ✓ No hardcoded credentials   │
│     ├─ OPA - Secure Coding                 ✓ No eval, shell=True        │
│     ├─ OPA - Dependencies                  ✓ Pinned versions            │
│     └─ OPA - Containers                    ✓ Non-root, no :latest       │
│                                                                           │
│  6. License Compliance                     [dependency-review.yml]       │
│     ├─ pip-licenses                        ✓ Allowed licenses only      │
│     ├─ Dependency confusion                ✓ No public conflicts        │
│     └─ Malicious packages                  ✓ Known bad actors           │
│                                                                           │
│  7. CI/CD Hardening                        [ci-hardening.yml]            │
│     ├─ Workflow linting                    ✓ actionlint validation      │
│     ├─ Action pinning                      ✓ SHA-based pins             │
│     ├─ Permission audit                    ✓ Minimal permissions        │
│     └─ Dangerous patterns                  ✓ No unsafe triggers         │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                         QUALITY PIPELINE                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. Code Coverage                          [ci.yml]                      │
│     ├─ Sharded execution (3 shards)        ✓ Parallel testing           │
│     ├─ Coverage threshold: 98%             ✓ Merge blocker              │
│     └─ Coverage aggregation                ✓ Combined report            │
│                                                                           │
│  2. Mutation Testing                       [ci.yml]                      │
│     ├─ mutmut (code mutations)             ✓ Test effectiveness         │
│     ├─ Kill rate threshold: 90%            ✓ Quality gate               │
│     └─ Critical path focus                 ✓ Core modules               │
│                                                                           │
│  3. Risk Assessment                        [pr-release-gate.yml]         │
│     ├─ Coverage gap analysis               ✓ Risk scoring               │
│     ├─ Mutation effectiveness              ✓ Automated labeling         │
│     ├─ Critical file changes               ✓ Risk level (low/med/high)  │
│     └─ PR size analysis                    ✓ Review complexity          │
│                                                                           │
│  4. Complexity Analysis                    [pr-complexity-analysis.yml]  │
│     ├─ Cyclomatic complexity               ✓ Avg <10, Max <15           │
│     ├─ Lines changed (<500 pref)           ✓ PR size guidance           │
│     ├─ Breaking change detection           ✓ API compatibility          │
│     └─ Code ownership                      ✓ 100% coverage required     │
│                                                                           │
│  5. Merge Guard                            [merge-guard.yml]             │
│     ├─ Label validation                    ✓ No quality-gate-failed     │
│     ├─ Workflow status check               ✓ All required checks pass   │
│     └─ Merge blocking                      ✓ Prevent premature merge    │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                      PERFORMANCE PIPELINE                                 │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. Benchmark Comparison                   [performance-regression-pr]   │
│     ├─ PR branch benchmarks                ✓ pytest-benchmark           │
│     ├─ Base branch benchmarks              ✓ 5+ runs for accuracy       │
│     ├─ Statistical comparison              ✓ Regression detection       │
│     └─ Threshold enforcement               ✓ >10% warn, >25% block      │
│                                                                           │
│  2. Memory Profiling                       [performance-regression-pr]   │
│     ├─ Memory usage tracking               ✓ memory-profiler            │
│     ├─ Peak memory comparison              ✓ >20% increase = warning    │
│     └─ Allocation patterns                 ✓ Leak detection             │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                   SUPPLY CHAIN SECURITY                                   │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. SLSA Provenance                        [slsa-provenance.yml]         │
│     ├─ Build metadata collection           ✓ SLSA Level 3               │
│     ├─ Sigstore signing                    ✓ Keyless attestation        │
│     └─ GitHub Attestations                 ✓ Verifiable provenance      │
│                                                                           │
│  2. OSSF Scorecard                         [ossf-scorecard.yml]          │
│     ├─ 18+ security checks                 ✓ Supply chain validation    │
│     ├─ Weekly + PR scanning                ✓ Trend monitoring           │
│     └─ SARIF upload                        ✓ Security tab integration   │
│                                                                           │
│  3. SBOM Generation                        [sbom-generation.yml]         │
│     ├─ SPDX 2.3 format                     ✓ ISO standard               │
│     ├─ CycloneDX 1.5 format                ✓ Modern SBOM                │
│     ├─ VEX document                        ✓ Exploitability data        │
│     ├─ Vulnerability scanning              ✓ Grype on SBOM              │
│     ├─ Sigstore signing                    ✓ Artifact integrity         │
│     └─ GitHub attestation                  ✓ Transparency log           │
│                                                                           │
│  4. Dependency Review                      [dependency-review.yml]       │
│     ├─ GitHub API integration              ✓ Automated review           │
│     ├─ License validation                  ✓ Compliance check           │
│     └─ Risk assessment                     ✓ New dependency approval    │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

                                 │
                                 │ ALL CHECKS PASS
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        PR QUALITY SUMMARY                                 │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Automated comment posted to PR with:                                    │
│                                                                           │
│  ✅ Code Coverage:              98.5% (target: 98%)                      │
│  ✅ Mutation Kill Rate:         92% (target: 90%)                        │
│  ✅ Security Scans:             0 critical issues                        │
│  ✅ License Compliance:         All allowed                              │
│  ✅ Performance:                No regressions                           │
│  ✅ Complexity:                 Avg: 8.2, Max: 12                        │
│  ✅ SLSA Provenance:            Generated & signed                       │
│  ✅ OSSF Scorecard:             9.2/10                                   │
│  ✅ SBOM:                       Generated & attested                     │
│  ✅ Policy Enforcement:         All policies pass                        │
│  ✅ Risk Level:                 LOW                                      │
│                                                                           │
│  Labels Applied:                                                         │
│  - risk: low                                                             │
│  - security-reviewed                                                     │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ READY FOR REVIEW
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      MERGE REQUIREMENTS                                   │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Branch Protection Rules (main):                                         │
│  ✓ 2+ approving reviews from CODEOWNERS                                 │
│  ✓ All required status checks pass                                      │
│  ✓ Conversations resolved                                               │
│  ✓ No quality-gate-failed label                                         │
│  ✓ Signed commits (recommended)                                         │
│  ✓ Up to date with base branch                                          │
│                                                                           │
│  Required Status Checks:                                                 │
│  1. Aggregate coverage & enforce guardrail                               │
│  2. Mutation Testing Gate (90% kill rate)                                │
│  3. Security Scan (secret-scan, dependency-scan, container-scan)         │
│  4. OSSF Scorecard                                                       │
│  5. License Compliance                                                   │
│  6. Policy Enforcement                                                   │
│  7. Performance Regression (if code changes)                             │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ ALL REQUIREMENTS MET
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                           MERGE TO MAIN                                   │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │
                    ┌────────────┴────────────┐
                    │  Post-Merge Actions      │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ SLSA          │      │ Container     │      │ Documentation │
│ Provenance    │      │ Publishing    │      │ Update        │
└───────────────┘      └───────────────┘      └───────────────┘
        │                        │                        │
        ├─ Sign artifacts        ├─ Sign images          ├─ CHANGELOG
        ├─ Generate attestation  ├─ Push to registry     └─ Release notes
        └─ Publish SBOM          └─ Update deployments
```

## Workflow Files

### Core CI/CD
1. **ci.yml** - Main CI pipeline (coverage, mutation testing, publishing)
2. **tests.yml** - Test suite execution
3. **coverage.yml** - Coverage reporting and enforcement

### Security
4. **security.yml** - Multi-layer security scanning
5. **semgrep.yml** - Semantic security analysis
6. **security-policy-enforcement.yml** - OPA policy checks
7. **ci-hardening.yml** - CI/CD security audit

### Supply Chain
8. **slsa-provenance.yml** - SLSA Level 3 attestation
9. **ossf-scorecard.yml** - Supply chain security scoring
10. **sbom-generation.yml** - SBOM generation and signing
11. **dependency-review.yml** - License and dependency validation

### Quality
12. **pr-quality-summary.yml** - Automated quality reporting
13. **pr-release-gate.yml** - Risk assessment and labeling
14. **pr-complexity-analysis.yml** - Complexity and size analysis
15. **merge-guard.yml** - Merge blocking on quality failures

### Performance
16. **performance-regression-pr.yml** - Benchmark comparison

### Additional
17. **dependabot.yml** - Automated dependency updates (config)
18. **release-drafter.yml** - Automated release notes

## Quality Metrics Dashboard

| Metric | Threshold | Current | Trend |
|--------|-----------|---------|-------|
| Code Coverage | ≥98% | 98.5% | ↗️ |
| Mutation Kill Rate | ≥90% | 92% | → |
| Security Issues | 0 critical | 0 | ✓ |
| Performance Regression | <10% | +2% | ↗️ |
| Avg Complexity | <10 | 8.2 | ↘️ |
| Max Complexity | <15 | 12 | ↘️ |
| OSSF Score | ≥8.0 | 9.2 | ↗️ |
| License Compliance | 100% | 100% | ✓ |

## Time to Feedback

| Check | Time | Parallel | Blocking |
|-------|------|----------|----------|
| Secret Scanning | 30s | Yes | Yes |
| SAST (Bandit) | 45s | Yes | Yes |
| SAST (Semgrep) | 2m | Yes | Yes |
| SAST (CodeQL) | 5m | Yes | No |
| Dependency Scan | 1m | Yes | Yes |
| Container Scan | 3m | Yes | Yes |
| Coverage | 8m | Yes (sharded) | Yes |
| Mutation Testing | 15m | Yes | Yes |
| Performance | 10m | Yes | Yes |
| Complexity Analysis | 1m | Yes | No |
| SLSA Provenance | 2m | No | No |
| OSSF Scorecard | 3m | Yes | No |
| SBOM Generation | 4m | Yes | No |

**Total Time (parallel)**: ~15-20 minutes
**Total Time (serial)**: ~55 minutes
**Efficiency Gain**: 65-70%

## Best Practices Implemented

### Security
✅ Multi-layer defense (7 security tools)
✅ Secret scanning in Git history
✅ SAST with 3 different engines
✅ Dependency scanning from 4 sources
✅ Container security with dual scanners
✅ Policy enforcement with OPA
✅ Supply chain security (SLSA L3)

### Quality
✅ 98% code coverage requirement
✅ 90% mutation kill rate
✅ Complexity limits enforced
✅ PR size guidance
✅ Automated risk assessment
✅ Breaking change detection

### Performance
✅ Automated benchmark comparison
✅ Memory profiling
✅ Regression detection
✅ Statistical validation

### Supply Chain
✅ SLSA Level 3 provenance
✅ OSSF Scorecard monitoring
✅ SBOM generation (SPDX + CycloneDX)
✅ Artifact signing (Sigstore)
✅ License compliance
✅ Dependency confusion protection

### CI/CD
✅ Workflow security audit
✅ Action pinning enforcement
✅ Minimal permissions
✅ OIDC authentication
✅ No dangerous patterns

## Continuous Improvement

### Monitoring
- Weekly OSSF Scorecard reviews
- Monthly security audit reports
- Quarterly policy updates
- Annual penetration testing

### Metrics Tracked
- Mean time to detection (MTTD)
- Mean time to resolution (MTTR)
- False positive rate
- Coverage trends
- Performance baselines

### Feedback Loop
1. **Collection**: Gather metrics from all workflows
2. **Analysis**: Identify trends and issues
3. **Action**: Update policies and thresholds
4. **Validation**: Verify improvements
5. **Documentation**: Update guides and standards

---

**Version**: 1.0
**Last Updated**: 2025-11-11
**Review Frequency**: Quarterly
**Owner**: DevSecOps Team
