# Metrics Contract: Claims vs Evidence

> **Purpose**: This document tracks all bold claims made in TradePulse documentation,
> their evidence status, and reproducibility instructions.
>
> **Last Updated**: 2025-12-10
> **Maintainer**: TradePulse Team

## Overview

TradePulse documentation makes various claims about coverage, performance, reliability,
and compliance. This contract explicitly tracks each claim's verification status to
maintain engineering integrity.

## Claims Registry

### Coverage Claims

| Claim | Location | Type | Status | How to Prove | Notes |
|-------|----------|------|--------|--------------|-------|
| "98% coverage target" | README.md:57, TESTING.md:59 | coverage | `target_not_current` | `make test-coverage` | Target for v1.0; current CI gate is 80% |
| "backtest/: 100%" | TESTING.md:64 | coverage | `partial_evidence` | Run coverage on backtest/ | Verify with actual coverage run |
| "execution/: 100%" | TESTING.md:65 | coverage | `partial_evidence` | Run coverage on execution/ | Verify with actual coverage run |

### Performance Claims

| Claim | Location | Type | Status | How to Prove | Notes |
|-------|----------|------|--------|--------------|-------|
| "1M+ bars/second throughput" | README.md:382 | perf_throughput | `design_goal` | Benchmark required | Design goal, not measured |
| "Sub-5ms order latency" | README.md:383 | perf_latency | `design_goal` | Benchmark with mock exchange | Exchange-dependent; design target |
| "Sub-1ms signal generation" | README.md:384 | perf_latency | `design_goal` | Indicator benchmark | With cached indicators only |
| "~200MB steady-state memory" | README.md:385 | memory | `design_goal` | Memory profiling | For live trading |
| "10-50x GPU speedup" | README.md:386 | perf_throughput | `planned` | GPU benchmark required | CUDA operations only |

### Reliability Claims

| Claim | Location | Type | Status | How to Prove | Notes |
|-------|----------|------|--------|--------------|-------|
| "production-grade" | README.md:14 | reliability | `qualified` | — | Beta status acknowledged in roadmap |
| "Enterprise-Grade" | README.md:55 | reliability | `qualified` | — | Patterns implemented, not production-proven |
| "TRL7 (post-staging)" | README.md:323 | reliability | `claimed` | Review TACL implementation | Internal classification |

### Security & Compliance Claims

| Claim | Location | Type | Status | How to Prove | Notes |
|-------|----------|------|--------|--------------|-------|
| "NIST SP 800-53 aligned" | README.md:104, SECURITY.md | security | `designed` | Security controls review | Controls designed, not externally audited |
| "ISO 27001 aligned" | README.md:55,104 | compliance | `designed` | Security controls review | Framework followed, no certification |
| "SEC, FINRA ready" | README.md:108, SECURITY.md | compliance | `designed` | Compliance review | Controls implemented, not audited |
| "GDPR, CCPA ready" | README.md:108 | compliance | `designed` | Privacy controls review | Controls present, no formal audit |
| "SOC 2" | SECURITY.md:11 | compliance | `designed` | Audit trail review | Telemetry present, no SOC 2 audit |
| "EU AI Act" | SECURITY.md:11 | compliance | `designed` | AI governance review | Human oversight patterns present |
| "93 controls" | README.md:104 | security | `partial_evidence` | Control inventory | Count derived from design docs |

### Testing Claims

| Claim | Location | Type | Status | How to Prove | Notes |
|-------|----------|------|--------|--------------|-------|
| "50+ indicators" | README.md:554 | feature | `partial_evidence` | Indicator count script | Need to verify actual count |
| "400-day audit retention" | README.md:97 | reliability | `designed` | Audit log config | Configuration exists, not production-verified |

## Evidence Status Definitions

| Status | Meaning |
|--------|---------|
| `fully_proven` | Verified by CI, reproducible with documented command, green logs available |
| `partial_evidence` | Some evidence exists but not fully reproducible or documented |
| `designed` | Implementation exists but no external verification or production evidence |
| `planned` | Feature is on roadmap but not yet implemented |
| `design_goal` | Target metric, not yet achieved or measured |
| `target_not_current` | Goal for future release, current state is different |
| `qualified` | Claim is accurate with stated qualifications |
| `claimed` | Internal classification without external validation |

## Reproducibility Instructions

### Coverage Verification

```bash
# Generate full coverage report
make test-coverage

# View HTML report
open reports/coverage/index.html

# Expected output location:
# - HTML: reports/coverage/index.html
# - XML: reports/coverage/coverage.xml
```

### Performance Verification

```bash
# Run performance benchmarks
make perf

# Generate performance report
python scripts/performance/generate_replay_report.py \
    --output-dir reports/performance \
    --generate-charts
```

### Security Verification

```bash
# Run security audits
make audit

# Full security scan
make security-test
```

## Verification Schedule

| Category | Frequency | Owner |
|----------|-----------|-------|
| Coverage | Every PR | CI (automated) |
| Performance | Weekly/Nightly | CI (optional) |
| Security | Every PR + Weekly | CI (automated) |
| Compliance | Quarterly | Security Team |

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-10 | Initial metrics contract created | TradePulse Team |

---

**Note**: This document is the source of truth for claim verification. All bold statements
in documentation should be traceable to entries in this contract with appropriate evidence
status.
