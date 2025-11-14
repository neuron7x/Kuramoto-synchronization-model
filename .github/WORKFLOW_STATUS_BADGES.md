# GitHub Actions Workflow Status Badges

This document provides information about workflow status badges that can be added to the README or other documentation.

## Core CI/CD Workflows

### Main Test Suite
```markdown
[![Tests](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)
```
[![Tests](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)

### Coverage
```markdown
[![Coverage](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml)
```
[![Coverage](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml)

### Security Scanning
```markdown
[![Security](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml)
```
[![Security](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml)

### CodeQL Analysis
```markdown
[![CodeQL](https://github.com/neuron7x/TradePulse/actions/workflows/codeql.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/codeql.yml)
```

### OSSF Scorecard
```markdown
[![OSSF Scorecard](https://github.com/neuron7x/TradePulse/actions/workflows/ossf-scorecard.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/ossf-scorecard.yml)
```
[![OSSF Scorecard](https://github.com/neuron7x/TradePulse/actions/workflows/ossf-scorecard.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/ossf-scorecard.yml)

## Infrastructure & Deployment

### Helm Charts
```markdown
[![Helm](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml)
```
[![Helm](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml)

### Publish Container Image
```markdown
[![Publish Image](https://github.com/neuron7x/TradePulse/actions/workflows/publish-image.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/publish-image.yml)
```
[![Publish Image](https://github.com/neuron7x/TradePulse/actions/workflows/publish-image.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/publish-image.yml)

### Deploy Environments
```markdown
[![Deploy](https://github.com/neuron7x/TradePulse/actions/workflows/deploy-environments.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/deploy-environments.yml)
```

## Quality Gates

### Mutation Testing
```markdown
[![Mutation Tests](https://github.com/neuron7x/TradePulse/actions/workflows/mutation-tests.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/mutation-tests.yml)
```
[![Mutation Tests](https://github.com/neuron7x/TradePulse/actions/workflows/mutation-tests.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/mutation-tests.yml)

### Performance Regression
```markdown
[![Performance](https://github.com/neuron7x/TradePulse/actions/workflows/performance-regression.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/performance-regression.yml)
```
[![Performance](https://github.com/neuron7x/TradePulse/actions/workflows/performance-regression.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/performance-regression.yml)

### Load Tests
```markdown
[![Load Tests](https://github.com/neuron7x/TradePulse/actions/workflows/load-test.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/load-test.yml)
```
[![Load Tests](https://github.com/neuron7x/TradePulse/actions/workflows/load-test.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/load-test.yml)

## Automation Workflows (New)

### PR Size Labeler
```markdown
[![PR Size Labeler](https://github.com/neuron7x/TradePulse/actions/workflows/pr-size-labeler.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/pr-size-labeler.yml)
```
[![PR Size Labeler](https://github.com/neuron7x/TradePulse/actions/workflows/pr-size-labeler.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/pr-size-labeler.yml)

### Stale Management
```markdown
[![Stale](https://github.com/neuron7x/TradePulse/actions/workflows/stale.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/stale.yml)
```
[![Stale](https://github.com/neuron7x/TradePulse/actions/workflows/stale.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/stale.yml)

### First Time Contributor Welcome
```markdown
[![Welcome](https://github.com/neuron7x/TradePulse/actions/workflows/first-time-contributor.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/first-time-contributor.yml)
```
[![Welcome](https://github.com/neuron7x/TradePulse/actions/workflows/first-time-contributor.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/first-time-contributor.yml)

### Changelog Automation
```markdown
[![Changelog](https://github.com/neuron7x/TradePulse/actions/workflows/changelog-automation.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/changelog-automation.yml)
```
[![Changelog](https://github.com/neuron7x/TradePulse/actions/workflows/changelog-automation.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/changelog-automation.yml)

## Usage in README

### Recommended Badge Group for README.md

Add this to your README.md to show the most important workflow statuses:

```markdown
## Build Status

[![Tests](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)
[![Coverage](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml)
[![Security](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml)
[![OSSF Scorecard](https://github.com/neuron7x/TradePulse/actions/workflows/ossf-scorecard.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/ossf-scorecard.yml)
[![Helm](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml)
```

### Compact Single-Line Version

```markdown
[![CI](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml) [![Security](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml) [![Helm](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml/badge.svg)](https://github.com/neuron7x/TradePulse/actions/workflows/helm.yml)
```

## Badge Customization

### Branch-Specific Badges

To show status for a specific branch:

```markdown
[![Tests](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)
```

### Event-Specific Badges

To show status for specific events:

```markdown
[![Tests](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg?event=push)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)
```

## Additional Resources

- [GitHub Actions Badge Documentation](https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/adding-a-workflow-status-badge)
- [Shields.io Custom Badges](https://shields.io/)
- [Workflow Status API](https://docs.github.com/en/rest/actions/workflows)

## Notes

- Badges automatically update when workflows run
- Green badge = passing, red badge = failing
- Click badge to see detailed workflow results
- Badges work in README.md, wiki pages, and documentation

---

**Last Updated**: 2025-11-14
**Maintained By**: TradePulse DevOps Team
