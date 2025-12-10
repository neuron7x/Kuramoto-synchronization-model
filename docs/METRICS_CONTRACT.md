# Metrics Contract: Claims vs Evidence

> **Purpose**: This document tracks all bold claims made in TradePulse documentation,
> their evidence status, and reproducibility instructions.
>
> **Last Updated**: 2025-12-10
> **Maintainer**: TradePulse Team

## ⚠️ Important Notice

This document requires regular maintenance. Claims and their statuses must be updated:
- When documentation changes
- After each release
- When evidence is collected or validated

**Do not rely on this document if it has not been updated in the last 30 days.**

## Overview

TradePulse documentation makes various claims about coverage, performance, reliability,
and compliance. This contract explicitly tracks each claim's verification status to
maintain engineering integrity.

## Claims Registry

### Coverage Claims

| Claim | Type | Status | How to Verify |
|-------|------|--------|---------------|
| "98% coverage v1.0 target" | coverage | `roadmap_goal` | `make test-coverage` → check actual % |
| "80% CI gate" | coverage | `enforced` | CI pipeline configuration in `.github/workflows/` |
| "backtest/: 100% goal" | coverage | `goal` | `pytest --cov=backtest tests/` |
| "execution/: 100% goal" | coverage | `goal` | `pytest --cov=execution tests/` |

### Performance Claims

| Claim | Type | Status | How to Verify |
|-------|------|--------|---------------|
| "1M+ bars/second" | perf | `design_target` | Run `make perf`, no verified benchmark yet |
| "Sub-5ms order latency" | perf | `design_target` | Exchange-dependent, needs live testing |
| "Sub-1ms signal generation" | perf | `design_target` | `pytest tests/performance/` |
| "~200MB memory" | memory | `design_target` | Memory profiling required |
| "GPU acceleration" | perf | `planned` | CUDA kernels in development |

### Reliability Claims

| Claim | Type | Status | How to Verify |
|-------|------|--------|---------------|
| "production-grade" | reliability | `beta` | See roadmap; live trading in development |
| "Enterprise-Grade" | reliability | `patterns_only` | Design patterns implemented, not battle-tested |
| "TRL7" | reliability | `internal_claim` | Internal assessment only |

### Security & Compliance Claims

| Claim | Type | Status | How to Verify |
|-------|------|--------|---------------|
| "NIST SP 800-53 aligned" | compliance | `design_aligned` | Controls designed, NO external audit |
| "ISO 27001 aligned" | compliance | `design_aligned` | Framework followed, NO certification |
| "SEC/FINRA patterns" | compliance | `design_aligned` | Controls present, NO regulatory audit |
| "GDPR/CCPA patterns" | compliance | `design_aligned` | Privacy controls, NO formal audit |
| "SOC 2" | compliance | `design_aligned` | Telemetry present, NO SOC 2 examination |

## Evidence Status Definitions

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| `enforced` | Verified by CI on every PR | None |
| `roadmap_goal` | Target for future release | Track progress |
| `goal` | Stated goal, not enforced | Consider enforcing |
| `design_target` | Architecture target, not measured | Create benchmarks |
| `planned` | On roadmap, not implemented | Track in backlog |
| `design_aligned` | Implementation matches framework, NO external audit | Consider audit |
| `patterns_only` | Design patterns present, not production-proven | Validate in production |
| `beta` | Feature in development | Monitor stability |
| `internal_claim` | Internal assessment only | Document methodology |

## Verification Commands

### Coverage

```bash
# Generate coverage report (fast tests only)
make test-coverage

# View HTML report
open reports/coverage/index.html

# Full coverage with all tests
pytest tests/ --cov=core --cov=backtest --cov=execution --cov-report=html:reports/coverage
```

### Performance

```bash
# Run performance benchmarks
make perf

# Run specific benchmark tests
pytest tests/performance/test_indicator_benchmarks.py --benchmark-enable
```

### Security

```bash
# Run security audits
make audit

# Run dependency audit
pip-audit -r requirements.txt
```

## Maintenance Requirements

1. **After each PR**: Update claims if documentation changes
2. **After each release**: Review all `roadmap_goal` items
3. **Quarterly**: Review compliance claims with security team
4. **Annually**: Consider external audit for `design_aligned` items

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-10 | Initial metrics contract - removed line numbers, added maintenance requirements | TradePulse Team |

---

**⚠️ WARNING**: This document does NOT constitute a security audit, compliance certification,
or performance guarantee. All claims with status other than `enforced` require independent
verification before relying on them for production decisions.
