# Repository Validation Health Score

## Weighted Scoring System

Health Score (0-100) uses category-based weights where Security, Tests, and Module Imports have highest impact.

### Category Weights

| Category | Weight | Impact |
|----------|--------|--------|
| Security | 25% | Vulnerabilities/secrets - production critical |
| Test Suite | 20% | Code quality - prevents regressions |
| Module Imports | 15% | Code integrity - broken imports = broken code |
| Code Integrity | 15% | Syntax errors block deployment |
| Configuration | 10% | Invalid configs cause runtime failures |
| Build System | 5% | Development workflow |
| Data Integrity | 5% | Data quality |
| Documentation | 3% | Important but non-blocking |
| File Integrity | 2% | Checksums |
| Git Repository | 0% | Informational only |

### Calculation

```
base_score = Σ(category_passed/category_total * category_weight * 100)
penalties = (ERROR_count * -3) + (WARNING_count * -0.5)
final_score = base_score - penalties

if has_CRITICAL_failures:
    max_score = 60  # Cap at 60/100
else:
    max_score = 100

health_score = max(0, min(max_score, int(final_score)))
```

### Overall Status

- **PASS**: No CRITICAL/ERROR failures
- **WARN**: Only WARNING failures (environment issues)
- **FAIL_CRITICAL**: Has CRITICAL/ERROR failures (blocks deployment)

### Score Interpretation

| Score | Status | Action |
|-------|--------|--------|
| 90-100 | Excellent | Production-ready |
| 70-89 | Good | Minor issues |
| 50-69 | Fair | Review warnings |
| 30-49 | Poor | Multiple failures |
| 0-29 | Critical | Not ready |

**Note:** CRITICAL failures cap score at 60, requiring immediate action.

See reports/REPOSITORY_VALIDATION_REPORT.md for detailed breakdown.
