# Metrics Contract: Claims vs Evidence

> **Purpose**: This document is the single source of truth for all claims made in TradePulse documentation.
> All coverage, performance, security, and compliance claims in README.md, TESTING.md, and SECURITY.md
> must reference this document for their evidence status.
>
> **Last Updated**: 2025-12-10
> **Maintainer**: TradePulse Team

## ⚠️ Important Notice

This document requires regular maintenance. Claims and their statuses must be updated:
- When documentation changes
- After each release
- When evidence is collected or validated

**Do not rely on this document if it has not been updated in the last 30 days.**

---

## Evidence Status Definitions

All claims use exactly one of these statuses:

| Status | Meaning | CI Verified? |
|--------|---------|--------------|
| `enforced` | Enforced by CI with `--cov-fail-under` or equivalent gate | ✅ Yes |
| `goal` | Stated module-level goal, not enforced in CI | ❌ No |
| `design_target` | Architecture target, not yet measured | ❌ No |
| `planned` | On roadmap, not implemented | ❌ No |
| `design_aligned` | Implementation follows framework, NO external audit | ❌ No |
| `internal_claim` | Internal assessment, no external validation | ❌ No |

---

## Claims Registry

### Coverage Claims

| Claim | Status | How to Verify | Notes |
|-------|--------|---------------|-------|
| 98% CI coverage gate | `enforced` | `.github/workflows/tests.yml` uses `--cov-fail-under=98` | Blocks PR if below 98% |
| backtest/ 100% | `goal` | `pytest --cov=backtest tests/` | Module goal, not enforced |
| execution/ 100% | `goal` | `pytest --cov=execution tests/` | Module goal, not enforced |
| core modules 90-95% | `goal` | `pytest --cov=core tests/` | Module goal, not enforced |

### Performance Claims

| Claim | Status | How to Verify | Notes |
|-------|--------|---------------|-------|
| 1M+ bars/second | `design_target` | `pytest tests/performance/` | No verified benchmark |
| Sub-5ms order latency | `design_target` | Exchange-dependent | Needs live testing |
| Sub-1ms signal generation | `design_target` | `pytest tests/performance/test_indicator_benchmarks.py` | Benchmark exists |
| ~200MB memory | `design_target` | Memory profiling | Not automated |
| GPU acceleration | `planned` | — | CUDA kernels not implemented |

### Reliability Claims

| Claim | Status | Notes |
|-------|--------|-------|
| production-grade | `design_target` | Live trading in beta |
| Enterprise-Grade | `design_aligned` | Patterns implemented, not battle-tested |
| TRL7 | `internal_claim` | Internal assessment only |

### Security & Compliance Claims

| Claim | Status | Notes |
|-------|--------|-------|
| NIST SP 800-53 aligned | `design_aligned` | Controls designed, NO external audit |
| ISO 27001 aligned | `design_aligned` | Framework followed, NO certification |
| SEC/FINRA patterns | `design_aligned` | Controls present, NO regulatory audit |
| GDPR/CCPA patterns | `design_aligned` | Privacy controls, NO formal audit |
| SOC 2 | `design_aligned` | Telemetry present, NO SOC 2 examination |

---

## Verification Commands

### Coverage

```bash
# Generate coverage report
make test-coverage

# View HTML report
open reports/coverage/index.html
```

### Security

```bash
# Run security audits (pip-audit + bandit)
make audit
```

### Performance

```bash
# Run performance benchmarks
make perf

# Run specific benchmark tests
pytest tests/performance/test_indicator_benchmarks.py --benchmark-enable
```

---

## Maintenance Requirements

1. **After each PR**: Update claims if documentation changes
2. **After each release**: Review all `goal` items
3. **Quarterly**: Review compliance claims with security team
4. **Annually**: Consider external audit for `design_aligned` items

---

**⚠️ WARNING**: This document does NOT constitute a security audit, compliance certification,
or performance guarantee. All claims with status other than `enforced` require independent
verification before relying on them for production decisions.
