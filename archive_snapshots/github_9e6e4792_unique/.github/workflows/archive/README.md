# Archived Workflows

This directory contains GitHub Actions workflows that are no longer actively used but are preserved for reference.

## Archived Workflows

### merge-guard.yml
**Status**: Deprecated  
**Reason**: Quality gates are now enforced by `tests.yml` and `pr-release-gate.yml`  
**Alternative**: Use the consolidated workflows instead

### pr-complexity-analysis.yml
**Status**: Deprecated  
**Reason**: Risk assessment is now handled in `pr-release-gate.yml`  
**Alternative**: Use `pr-release-gate.yml` for PR quality checks

### pr-quality-labels.yml
**Status**: Deprecated  
**Reason**: Labels are now managed by `pr-release-gate.yml`  
**Alternative**: Use `pr-release-gate.yml` for automatic labeling

### pr-quality-summary.yml
**Status**: Deprecated  
**Reason**: Use `tests.yml` comments for PR summaries instead  
**Alternative**: See test results in `tests.yml` workflow runs

### performance-regression-pr.yml
**Status**: Deprecated  
**Reason**: Redundant with `performance-regression.yml` - both workflows trigger on PRs causing duplicate CI runs  
**Alternative**: Use `performance-regression.yml` which runs on ALL PRs and already covers all performance-critical paths

---

**Note**: These workflows were disabled (set to `workflow_dispatch` only with no automatic triggers) before being archived. They can be restored if needed, but the consolidated workflows provide the same functionality with better maintainability.
