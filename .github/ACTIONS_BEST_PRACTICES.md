# GitHub Actions Best Practices (2025 Edition)

## Overview
This document outlines the best practices implemented in TradePulse GitHub Actions workflows, aligned with 2025 industry standards and our neuro-inspired trading architecture.

## Core Principles

### 1. **Explicit Timeouts**
All jobs and long-running steps have explicit timeouts to prevent resource waste and catch hanging processes.

```yaml
jobs:
  my-job:
    timeout-minutes: 30  # Job-level timeout
    steps:
      - name: Long task
        run: ./script.sh
        timeout-minutes: 20  # Step-level timeout
```

**Rationale**: Prevents runaway workflows that consume GitHub Actions minutes and delay other jobs.

### 2. **Smart Test Selection**
Run only tests relevant to changed files, reducing CI time by 60%+ while maintaining quality.

```yaml
# Automatically detects changed modules and runs only relevant tests
- uses: dorny/paths-filter@v3
  with:
    filters: |
      core:
        - 'core/**/*.py'
```

**Rationale**: Neural efficiency - test only what's needed, similar to selective attention in the brain.

### 3. **Performance Regression Detection**
Automated benchmarking on every PR to catch performance degradation early.

```yaml
# Compares PR performance vs base branch
pytest bench/ \
  --benchmark-only \
  --benchmark-json=pr-benchmark.json \
  --benchmark-min-rounds=5
```

**Rationale**: Critical for high-frequency trading systems where milliseconds matter.

### 4. **Artifact Lifecycle Management**
Proper retention policies to avoid storage bloat while keeping essential data.

```yaml
- uses: actions/upload-artifact@v4
  with:
    retention-days: 7  # Auto-cleanup after 7 days
```

**Rationale**: Cost optimization and compliance with data retention policies.

### 5. **Workflow Health Monitoring**
Automated tracking of workflow performance and reliability.

**Metrics Tracked**:
- Success rate (alert if < 90%)
- Average duration (alert if > 30 min)
- Failure patterns
- Flaky test detection

**Rationale**: Proactive CI/CD management, catch issues before they become critical.

## Workflow Structure

### Required Permissions (Principle of Least Privilege)

```yaml
permissions:
  contents: read        # Always required
  pull-requests: write  # If commenting on PRs
  actions: read        # If analyzing other workflows
  security-events: write # If using CodeQL/security scanning
```

### Concurrency Control

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true  # Cancel outdated runs
```

### Environment Variables

```yaml
env:
  PYTHONUNBUFFERED: "1"      # Real-time logging
  PYTEST_ADDOPTS: "--strict-markers --tb=short"
  PIP_DISABLE_PIP_VERSION_CHECK: "1"
```

## Performance Optimizations

### 1. **Effective Caching**

```yaml
- uses: actions/setup-python@v6
  with:
    cache: 'pip'
    cache-dependency-path: |
      requirements.txt
      requirements.lock
      requirements-dev.txt
```

### 2. **Parallel Job Execution**

```yaml
strategy:
  fail-fast: false    # Let all jobs run for better debugging
  matrix:
    shard: [1, 2, 3]  # Parallel test execution
```

### 3. **Conditional Job Execution**

```yaml
jobs:
  expensive-tests:
    if: github.event_name == 'pull_request'  # Skip on push
```

## Security Best Practices

### 1. **Secret Scanning**
- Gitleaks for historical commits
- TruffleHog for verified secrets
- Custom scanners for privileged modules

### 2. **Dependency Scanning**
```yaml
- name: Run pip-audit
  run: pip-audit --require-hashes --strict
```

### 3. **SBOM Generation**
Software Bill of Materials for compliance and security audits.

## Testing Strategy

### Test Pyramid
1. **Unit Tests** (fast, isolated)
   - Core logic, algorithms, utilities
   - Target: < 5 seconds per module
   
2. **Integration Tests** (medium speed)
   - Module interactions, API contracts
   - Target: < 30 seconds per test suite
   
3. **E2E Tests** (slow, comprehensive)
   - Full system behavior
   - Run selectively or on schedule

### Coverage Requirements
- Line coverage: ≥ 90%
- Branch coverage: ≥ 90%
- Critical path coverage: 100%

### Flaky Test Management
```yaml
pytest -m "not flaky" tests/
--flaky-report=reports/flaky-tests-skipped.json
```

## Neuro-Trading Specific Requirements

### 1. **Latency Validation**
Critical trading paths must maintain sub-millisecond latencies:
- Order submission → acknowledgment: P99 < 10ms
- Market data processing: P95 < 1ms
- Signal generation: P99 < 5ms

### 2. **Neural Controller Testing**
Specialized tests for brain-inspired components:
- Basal ganglia action selection
- Dopamine prediction error learning
- Threat circuit risk management

### 3. **Thermodynamic Validation**
Ensure system entropy and energy metrics remain within bounds:
```python
assert system.entropy() < entropy_threshold
assert system.free_energy() > min_threshold
```

## Workflow Organization

### Primary Workflows
1. **tests.yml** - Comprehensive test suite
2. **ci.yml** - Coverage-focused CI with sharding
3. **security.yml** - Security scanning and auditing

### Optimization Workflows
4. **smart-tests.yml** - Selective testing based on changes
5. **perf-regression.yml** - Performance benchmarking
6. **workflow-health.yml** - CI/CD metrics and monitoring

### Specialty Workflows
7. **deploy-environments.yml** - Multi-environment deployment
8. **enterprise-cicd.yml** - Enterprise-grade quality gates
9. **mlops-orchestration.yml** - ML pipeline management

## Maintenance Guidelines

### Weekly Tasks
- [ ] Review workflow health metrics
- [ ] Update flaky test annotations
- [ ] Prune stale branches and artifacts

### Monthly Tasks
- [ ] Update action versions
- [ ] Review and optimize timeouts
- [ ] Analyze performance trends

### Quarterly Tasks
- [ ] Audit security scanning coverage
- [ ] Review and update testing strategy
- [ ] Benchmark optimization improvements

## Debugging Failed Workflows

### 1. **Check Logs**
```bash
gh run view <run-id> --log-failed
```

### 2. **Common Issues**
- **Timeout**: Increase timeout or optimize step
- **Flaky test**: Mark with @pytest.mark.flaky
- **Dependency conflict**: Check constraints/security.txt
- **OOM**: Reduce parallelism or increase runner size

### 3. **Re-running Jobs**
```yaml
- uses: nick-fields/retry@v2
  with:
    timeout_minutes: 10
    max_attempts: 3
    command: pytest tests/flaky/
```

## Metrics and KPIs

### Workflow Health
- **Success Rate**: ≥ 95%
- **Mean Duration**: < 15 minutes
- **P95 Duration**: < 25 minutes

### Test Quality
- **Flaky Rate**: < 2%
- **False Positive Rate**: < 1%
- **Coverage**: ≥ 90%

### Cost Efficiency
- **Minutes per PR**: < 50
- **Artifact Storage**: < 5GB/week
- **Cache Hit Rate**: ≥ 80%

## Future Enhancements

### Planned Additions
1. **AI-Powered Test Selection**
   - ML model predicts which tests to run based on code changes
   - Historical failure pattern analysis

2. **Dynamic Resource Allocation**
   - Adjust runner size based on workload
   - Auto-scale test parallelism

3. **Chaos Engineering**
   - Automated fault injection in test environments
   - Resilience validation

4. **Canary Deployments**
   - Gradual rollout with automatic rollback
   - Real-time monitoring integration

## References

### GitHub Actions Documentation
- [Workflow syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Security hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [Best practices](https://docs.github.com/en/actions/using-workflows/about-workflows#best-practices)

### Industry Standards
- [OpenSSF Scorecard](https://github.com/ossf/scorecard)
- [SLSA Framework](https://slsa.dev/)
- [CII Best Practices](https://bestpractices.coreinfrastructure.org/)

### Internal Documentation
- [TESTING.md](../TESTING.md) - Testing strategy
- [SECURITY.md](../SECURITY.md) - Security policies
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines

---

**Last Updated**: 2025-11-09
**Maintained by**: TradePulse DevOps Team
**Review Cycle**: Quarterly
