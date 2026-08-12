# GitHub Actions Workflows Summary

This document provides an overview of all active CI/CD workflows in the GeoSync repository.

## Core CI/CD Workflows

### Pull Request Workflows (Triggered on PRs)

| Workflow | File | Purpose | When |
|----------|------|---------|------|
| **Tests** | `tests.yml` | Primary PR gate: lint/type checks, fast unit/integration tests, coverage reporting (full 98% coverage gate runs only on main/schedule) | Every PR |
| **Reliability Smoke** | `reliability-smoke.yml` | Fast failure-mode smoke tests | Every PR, push to main/develop |
| **Security Policy Enforcement** | `security-policy-enforcement.yml` | Security scans for PRs (bandit, pip-audit, OPA policies) | PRs to main/develop |
| **Contract & Schema Validation** | `contract-schema-validation.yml` | Validate API contracts and schemas | PRs touching schemas/contracts/api |
| **Performance Regression** | `performance-regression.yml` | Detect performance regressions (20% threshold) | PRs (excluding docs) |
| **Performance Regression PR** | `performance-regression-pr.yml` | Targeted performance tests for critical paths | PRs to main/develop touching core/execution |
| **Version Gate** | `version-gate.yml` | Ensure version is bumped for releases | PRs to main/develop |
| **PR Release Gate** | `pr-release-gate.yml` | Quality & risk assessment for PRs | PRs to main/develop |
| **Dependency Review** | `dependency-review.yml` | License compliance and vulnerability checks | PRs touching dependencies |
| **Dependency Pinning** | `dependency-pinning.yml` | Enforce pinned dependencies | PRs touching dependencies |
| **Dependabot Auto Merge** | `dependabot-auto-merge.yml` | Safely auto-merge Dependabot patch/minor updates (same-repo only) | Dependabot PRs |
| **Pin Terraform Version** | `pin-terraform-version.yml` | Validate Terraform version and tests | PRs to main and pushes to main |
| **E2E Integration** | `e2e-integration.yml` | End-to-end integration tests | PRs touching tests/e2e or core modules |
| **Helm** | `helm.yml` | Validate Helm charts | PRs touching deploy/helm |
| **NAK CI** | `nak-ci.yml` | NAK controller specific tests | PRs touching nak_controller |
| **Neural Controller CI** | `neural-controller-ci.yml` | Neural controller tests | PRs touching geosync/neural_controller |
| **Multi-Exchange Replay** | `multi-exchange-replay-regression.yml` | Replay tests for exchange compatibility | PRs touching fixtures/recordings or backtest |

### Main Branch Workflows (Post-Merge)

| Workflow | File | Purpose | When |
|----------|------|---------|------|
| **CI - Test Coverage** | `ci.yml` | Coverage tracking and mutation testing on main | Push to main only |
| **Security Scan** | `security.yml` | Comprehensive security scanning | Push to main/develop |
| **Semgrep** | `semgrep.yml` | Static analysis security testing | Push to main/develop |
| **Mutation Testing** | `mutation-testing.yml` | Quality gate with 90% kill rate | Push to main/develop (code changes) |
| **Build Wheels** | `build-wheels.yml` | Build and verify Python wheels | Push to main/master |
| **SBOM** | `sbom.yml` | Generate Software Bill of Materials | Push to main/develop |
| **SBOM Generation** | `sbom-generation.yml` | Comprehensive SBOM with CycloneDX | Push to main, releases |
| **Dopamine Validation** | `dopamine-validation.yml` | Validate dopamine config changes | Push touching dopamine configs |
| **Thermo Evolution** | `thermo-evolution.yml` | Thermodynamic validation | Push to main touching evolution/tacl |
| **Enterprise CI/CD** | `enterprise-cicd.yml` | Enterprise deployment pipeline | Push to main, manual |
| **Release Drafter** | `release-drafter.yml` | Auto-generate release notes | Push to main |
| **Progressive Release Gates** | `progressive-release-gates.yml` | Progressive rollout validation | Push to main, manual |
| **OSSF Scorecard** | `ossf-scorecard.yml` | Supply chain security assessment | Weekly, push to main |
| **CI Hardening** | `ci-hardening.yml` | Validate CI/CD pipeline security | PRs/pushes touching workflows |

### Release Workflows (Triggered on Tags/Releases)

| Workflow | File | Purpose | When |
|----------|------|---------|------|
| **Publish Python** | `publish-python.yml` | Publish package to PyPI | Release published |
| **Publish Image** | `publish-image.yml` | Publish signed container images | Release published |
| **SLSA Provenance** | `slsa-provenance.yml` | Generate SLSA provenance | Release published, CI completion on main |

### Scheduled Workflows (Nightly/Weekly)

| Workflow | File | Purpose | Schedule |
|----------|------|---------|----------|
| **Canaries** | `canaries.yml` | Python version compatibility tests | Weekly (Monday 6am) |
| **Mutation Tests** | `mutation-tests.yml` | Weekly mutation testing | Weekly (Monday 3am) |
| **Exchange Canary** | `exchange-canary.yml` | Test exchange connectivity | Daily (2am) |
| **Exchange Matrix** | `exchange-matrix.yml` | Update exchange compatibility | Daily (3am) |
| **Smoke E2E** | `smoke-e2e.yml` | Nightly smoke tests | Daily (2am) |

### Manual/On-Demand Workflows

| Workflow | File | Purpose |
|----------|------|---------|
| **Load Test** | `load-test.yml` | Performance load testing (expensive) |
| **MLOps Orchestration** | `mlops-orchestration.yml` | ML pipeline orchestration |
| **Progressive Rollout** | `progressive-rollout.yml` | Manual progressive deployment |
| **SLO Gate** | `slo-gate.yml` | SLO validation and auto-rollback |

### Deployment Workflows

| Workflow | File | Purpose | When |
|----------|------|---------|------|
| **Deploy Environments** | `deploy-environments.yml` | Deploy to staging/production | Push to staging/production branches |

## Archived Workflows

The following workflows have been deprecated and moved to `.github/workflows/archive/`:

- `merge-guard.yml` - Replaced by `tests.yml` and `pr-release-gate.yml`
- `pr-complexity-analysis.yml` - Replaced by `pr-release-gate.yml`
- `pr-quality-labels.yml` - Replaced by `pr-release-gate.yml`
- `pr-quality-summary.yml` - Replaced by `tests.yml` comments

See `.github/workflows/archive/README.md` for details.

## Workflow Dependencies

```
Pull Request → tests.yml (lint, test, type-check)
            → security-policy-enforcement.yml
            → performance-regression.yml
            → pr-release-gate.yml (quality gates)
            ↓
Main Branch → ci.yml (coverage, mutation testing)
           → security.yml + semgrep.yml
           → build-wheels.yml
           → sbom-generation.yml
           ↓
Release    → publish-python.yml (PyPI)
          → publish-image.yml (GHCR, Docker Hub)
          → slsa-provenance.yml
```

## Best Practices

1. **For PRs**: Ensure `tests.yml` passes before merging
2. **Security**: All security scans must pass (no HIGH/CRITICAL findings)
3. **Coverage**: Full test suite enforces a 98% gate on main/scheduled runs; PR fast gates report coverage but do not enforce it. Keep improving coverage towards the target.
4. **Performance**: Performance regression workflows flag deviations beyond the configured 20% threshold
5. **Mutation Testing**: 90% kill rate required on main branch

## Maintenance

- **Add new workflows**: Follow the naming convention and update this document
- **Deprecate workflows**: Move to `archive/` and update `archive/README.md`
- **Modify triggers**: Consider impact on CI costs and developer experience
- **Regular review**: Quarterly review of workflow efficiency and costs

---

Last updated: 2025-12-12
