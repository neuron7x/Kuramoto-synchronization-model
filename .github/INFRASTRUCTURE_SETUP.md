# GitHub Infrastructure Configuration Guide

This document provides step-by-step instructions for manual GitHub repository configuration that cannot be automated via workflow files.

## 1. Branch Protection Rules

Configure branch protection for the `main` branch to enforce code quality and security standards.

### Steps:
1. Navigate to: **Settings** → **Branches** → **Add rule**
2. Branch name pattern: `main`
3. Configure the following settings:

#### Pull Request Requirements
- ✅ **Require a pull request before merging**
  - Required approvals: 1
  - ✅ **Require review from Code Owners**
  - ✅ **Dismiss stale pull request approvals when new commits are pushed**
  - ✅ **Require approval of the most recent reviewable push**

#### Status Checks
- ✅ **Require status checks to pass before merging**
  - ✅ **Require branches to be up to date before merging**
  - Select the following required checks:
    - `Tests / lint (3.11)` - Linting and type checking
    - `Tests / tests (3.11)` - Unit and integration tests
    - `Security Scan / secret-scan` - Secret detection
    - `Security Scan / dependency-scan` - Dependency vulnerability scan
    - `Security Scan / codeql-analysis (python)` - CodeQL Python analysis
    - `Semgrep Security Scan / semgrep` - Semgrep security scan

#### Additional Protections
- ✅ **Require conversation resolution before merging**
- ✅ **Do not allow bypassing the above settings**
  - This enforces the rules even for administrators

### Verification:
- Create a test PR and verify:
  - Cannot merge without Code Owner approval
  - Cannot merge with failing checks
  - Stale approvals are dismissed on new commits

---

## 2. Environment Protection

Configure deployment environments with protection rules to prevent unauthorized or accidental deployments.

### Staging Environment

#### Steps:
1. Navigate to: **Settings** → **Environments** → **New environment**
2. Name: `staging`
3. Configure:
   - **Deployment branches**: `staging` branch only
   - **Environment secrets**:
     - `AWS_REGION` - AWS region (e.g., `us-east-1`)
     - `AWS_STAGING_ROLE_ARN` - IAM role ARN for staging deployments
     - `AWS_STAGING_CLUSTER_NAME` - EKS cluster name for staging
   - Optional: **Wait timer** - 0 minutes (no wait for staging)
   - Optional: **Required reviewers** - Not required for staging (auto-deploy on passing checks)

### Production Environment

#### Steps:
1. Navigate to: **Settings** → **Environments** → **New environment**
2. Name: `production`
3. Configure:
   - **Deployment branches**: `production` branch only
   - ✅ **Required reviewers**: Add at least 1-2 maintainers/admins
   - **Environment secrets**:
     - `AWS_REGION` - AWS region for production (e.g., `us-west-2`)
     - `AWS_PRODUCTION_ROLE_ARN` - IAM role ARN for production deployments
     - `AWS_PRODUCTION_CLUSTER_NAME` - EKS cluster name for production
   - Optional: **Wait timer** - 5-10 minutes (cooling period before deployment)
   - ✅ **Prevent self-review** - Enabled

### Additional Environment Secrets (Optional)

If using external services, add these secrets to appropriate environments:

- `CODECOV_TOKEN` - Codecov upload token (staging/production)
- `SEMGREP_APP_TOKEN` - Semgrep Cloud token (for advanced scanning)
- `GITLEAKS_LICENSE` - Gitleaks license key (if using enterprise version)
- `COSIGN_CERTIFICATE_IDENTITY` - For SBOM signing verification
- `COSIGN_CERTIFICATE_OIDC_ISSUER` - OIDC issuer for Sigstore

### Verification:
- Trigger a deployment workflow manually via **Actions** → workflow → **Run workflow**
- Verify for production:
  - Deployment waits for reviewer approval
  - Cannot proceed without approval from required reviewers
- Verify secrets are properly scoped to environments

---

## 3. Repository Secrets

Configure repository-level secrets that are used across multiple workflows.

### Steps:
1. Navigate to: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
2. Add the following secrets:

#### Required Secrets:
- `GITHUB_TOKEN` - Automatically provided by GitHub Actions (no action needed)

#### Optional Secrets:
- `CODECOV_TOKEN` - For code coverage uploads to Codecov
- `SEMGREP_APP_TOKEN` - For Semgrep Cloud integration
- `GITLEAKS_LICENSE` - For Gitleaks enterprise features
- `COSIGN_CERTIFICATE_IDENTITY` - For SBOM signature verification
  - Example: `https://github.com/neuron7x/TradePulse/.github/workflows/sbom.yml@refs/heads/main`
- `COSIGN_CERTIFICATE_OIDC_ISSUER` - OIDC issuer URL
  - Example: `https://token.actions.githubusercontent.com`

### Verification:
- Check workflow runs that use secrets to ensure they complete successfully
- Verify secrets are not exposed in logs (GitHub masks them automatically)

---

## 4. Code Scanning Configuration

Enable GitHub's native code scanning features for security vulnerability detection.

### Steps:
1. Navigate to: **Settings** → **Code security and analysis**
2. Enable the following features:
   - ✅ **Dependency graph** - Automatically enabled
   - ✅ **Dependabot alerts** - Enable
   - ✅ **Dependabot security updates** - Enable
   - ✅ **Code scanning** - Already enabled via workflows
   - ✅ **Secret scanning** - Enable (free for public repos, requires plan for private)
   - ✅ **Secret scanning push protection** - Enable

### Verification:
1. Navigate to: **Security** → **Code scanning**
   - Verify alerts are visible from Semgrep and CodeQL workflows
2. Navigate to: **Security** → **Dependabot**
   - Verify Dependabot is creating alerts and PRs
3. Navigate to: **Security** → **Secret scanning**
   - Verify no secrets are detected in the repository

---

## 5. Actions Permissions

Configure GitHub Actions permissions to follow the principle of least privilege.

### Steps:
1. Navigate to: **Settings** → **Actions** → **General**
2. Under **Actions permissions**:
   - Select: ✅ **Allow all actions and reusable workflows**
   - Or: **Allow select actions and reusable workflows** (recommended for stricter control)
3. Under **Workflow permissions**:
   - Select: ✅ **Read repository contents and packages permissions**
   - ✅ **Allow GitHub Actions to create and approve pull requests** (needed for Dependabot auto-merge)
4. Under **Fork pull request workflows**:
   - ✅ **Require approval for all outside collaborators**
   - ❌ **Do NOT** send write tokens to workflows from fork pull requests
   - ❌ **Do NOT** send secrets to workflows from fork pull requests

### Verification:
- Create a fork and open a PR to verify approval is required
- Check that fork PRs cannot access secrets

---

## 6. CODEOWNERS Configuration

The `.github/CODEOWNERS` file is already configured, but ensure it's enforced:

### Current Configuration:
```
* @neuron7x
/core/ @neuron7x
/execution/ @neuron7x
/analytics/ @neuron7x
/apps/ @neuron7x
/ui/ @neuron7x
/tests/ @neuron7x
/docs/ @neuron7x
```

### Verification:
1. Create a test PR modifying any file
2. Verify @neuron7x is automatically requested as a reviewer
3. Verify PR cannot be merged without @neuron7x approval (due to branch protection)

---

## 7. Dependabot Configuration

Dependabot is configured via `.github/dependabot.yml` but requires enabling in repository settings.

### Steps:
1. Navigate to: **Settings** → **Code security and analysis**
2. Ensure **Dependabot version updates** is enabled
3. Dependabot will automatically create PRs based on the configuration

### Monitoring:
- Navigate to: **Insights** → **Dependency graph** → **Dependabot**
- Review open Dependabot PRs regularly
- Auto-merge is configured for patch and minor updates with passing CI

---

## 8. Required Status Checks Summary

Based on the workflows configured, these are the critical checks that should be required:

### Core Checks (Required):
- `Tests / lint` - Python linting and type checking
- `Tests / tests` - Core test suite
- `Security Scan / secret-scan` - Secret detection
- `Security Scan / codeql-analysis (python)` - CodeQL Python
- `Semgrep Security Scan / semgrep` - Semgrep scan

### Additional Checks (Optional but Recommended):
- `Tests / web-lint` - Frontend linting (if UI changes)
- `Tests / security-tests` - Security test suite
- `Security Scan / dependency-scan` - Dependency vulnerabilities
- `Security Scan / container-scan` - Container image scanning
- `E2E Integration Tests / e2e` - End-to-end tests

### Monitoring Checks (Should NOT block merge):
- `Python Version Canaries` - Python version compatibility (set `continue-on-error: true`)
- `Performance Regression Detection` - Performance benchmarks (optional gate)
- `Mutation Tests` - Mutation testing (runs on schedule)

---

## Maintenance Checklist

### Weekly:
- [ ] Review Dependabot PRs and merge safe updates
- [ ] Check Security alerts and address critical/high vulnerabilities
- [ ] Review failed scheduled workflows (canaries, mutation tests)

### Monthly:
- [ ] Audit environment secrets for expiration
- [ ] Review branch protection rules for effectiveness
- [ ] Check workflow run minutes usage and optimize if needed
- [ ] Update this documentation with any configuration changes

### Quarterly:
- [ ] Review and update CODEOWNERS file
- [ ] Audit repository access and permissions
- [ ] Review security scanning results trends
- [ ] Update Dependabot configuration for new ecosystems

---

## Troubleshooting

### Dependabot PRs Not Auto-Merging
- Verify branch protection allows auto-merge
- Check that all required status checks pass
- Ensure update is patch or minor (not major)
- Check workflow logs for `dependabot-auto-merge.yml`

### Code Scanning Not Showing Results
- Verify workflows completed successfully
- Check SARIF upload steps in security workflows
- Ensure `security-events: write` permission is set
- Navigate to Security tab and manually verify

### Environment Deployments Failing
- Verify environment secrets are correctly configured
- Check AWS IAM role trust relationships
- Verify EKS cluster names and regions are correct
- Review workflow logs for specific error messages

### Fork PRs Cannot Run Workflows
- This is expected behavior for security
- Outside collaborators must be approved manually
- Secrets are intentionally not available to forks
- Consider enabling specific workflows for forks if needed

---

## References

- [GitHub Branch Protection Documentation](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
- [GitHub Environments Documentation](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- [Dependabot Configuration Options](https://docs.github.com/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
- [GitHub Actions Security Hardening](https://docs.github.com/actions/security-guides/security-hardening-for-github-actions)
- [CODEOWNERS Documentation](https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [Code Scanning Documentation](https://docs.github.com/code-security/code-scanning)
