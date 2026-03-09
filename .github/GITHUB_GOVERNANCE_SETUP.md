# GitHub governance rollout checklist (TradePulse)

This repository contains the CI/CD control-plane workflows required for PR gate, security, nightly validation, release provenance, and deploy environments.

## Required repository settings (manual in GitHub UI)
1. Create a ruleset for `main`:
   - Require pull request before merging.
   - Require status checks:
     - `pr-gate / final`
     - `CodeQL / CodeQL`
     - `Dependency Review / Dependency Review`
   - Require code owner review.
   - Dismiss stale approvals.
   - Require conversation resolution.
   - Block force pushes and branch deletion.
   - Require signed commits.
   - Restrict direct pushes.
   - Enable merge queue.
2. Enable merge queue on `main`.
3. Enable GitHub Advanced Security features:
   - Code scanning (CodeQL)
   - Dependency review
   - Secret scanning
   - Push protection
   - Dependabot alerts + updates
   - Custom secret patterns for exchange/API credentials.
4. Configure environments:
   - `staging`: required reviewer = 1.
   - `production`: required reviewers = 1-2, manual approval.
5. Prefer OIDC federation for cloud auth and avoid long-lived repository secrets.

## Active workflow surface
- `.github/workflows/pr-gate.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/dependency-review.yml`
- `.github/workflows/nightly-quality.yml`
- `.github/workflows/release-supply-chain.yml`
- `.github/workflows/deploy.yml`
- `.github/workflows/_reusable-python-test.yml`
- `.github/workflows/_reusable-crypto-validation.yml`

Legacy workflows were moved to `.github/workflows-archive/`.
