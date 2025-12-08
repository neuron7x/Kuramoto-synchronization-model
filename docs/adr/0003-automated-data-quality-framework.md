# ADR-0003: Automated Data Quality Validation Framework

## Status
Accepted

**Date:** 2025-11-18

**Decision makers:** Principal System Architect, Data Platform Guild, Reliability Guild

**Related Requirements:** REQ-002

## Context

Market data quality issues cause:
- **Silent Failures:** Invalid data propagates through the system undetected
- **Incorrect Signals:** Indicators produce garbage outputs from corrupted data
- **Backtest Invalidity:** Historical simulations using flawed data are meaningless
- **Financial Risk:** Live trading on bad data leads to losses

Common data quality issues:
1. **Temporal gaps:** Missing bars in time series
2. **Price anomalies:** Impossible price movements (e.g., 50% single-bar spike)
3. **Volume zeros:** No trading activity reported
4. **OHLC violations:** High < Low, Close outside [Low, High]
5. **Duplicates:** Same timestamp appears multiple times
6. **Schema drift:** Column types change unexpectedly

Manual inspection is insufficient at scale (millions of bars per day). The system needs **automated quality validation** that:
- Detects issues immediately upon ingestion
- Blocks corrupt data from entering the system
- Provides detailed diagnostics for remediation
- Maintains audit trail of all quality checks

## Decision

We will implement an **Automated Data Quality Validation Framework** with:

### 1. Quality Rule Engine

**Location:** `core/data/quality/`

**Components:**
- `validators.py` - Pluggable validation rules
- `engine.py` - Orchestrates validation execution
- `reporter.py` - Generates quality reports
- `exceptions.py` - Quality-specific exception types

**Rule Types:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ValidationResult:
    rule_name: str
    passed: bool
    failures: list[dict[str, Any]]
    severity: str  # "error", "warning", "info"

class QualityRule(ABC):
    """Base class for quality validation rules."""
    
    @abstractmethod
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate data and return result."""
        pass

# Example rules
class TemporalContinuityRule(QualityRule):
    """Check for gaps in time series."""
    
    def __init__(self, expected_interval: timedelta, tolerance: timedelta):
        self.expected_interval = expected_interval
        self.tolerance = tolerance
    
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        gaps = []
        for i in range(len(data) - 1):
            actual_gap = data.index[i+1] - data.index[i]
            expected = self.expected_interval
            
            if abs(actual_gap - expected) > self.tolerance:
                gaps.append({
                    "from": data.index[i],
                    "to": data.index[i+1],
                    "expected": expected,
                    "actual": actual_gap
                })
        
        return ValidationResult(
            rule_name="temporal_continuity",
            passed=len(gaps) == 0,
            failures=gaps,
            severity="error"
        )

class OHLCConsistencyRule(QualityRule):
    """Validate OHLC relationships."""
    
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        violations = []
        
        # Check: High >= Low
        invalid_high_low = data[data["high"] < data["low"]]
        for idx, row in invalid_high_low.iterrows():
            violations.append({
                "timestamp": idx,
                "type": "high_less_than_low",
                "high": row["high"],
                "low": row["low"]
            })
        
        # Check: Open and Close within [Low, High]
        invalid_open = data[(data["open"] < data["low"]) | (data["open"] > data["high"])]
        for idx, row in invalid_open.iterrows():
            violations.append({
                "timestamp": idx,
                "type": "open_outside_range",
                "open": row["open"],
                "low": row["low"],
                "high": row["high"]
            })
        
        # Similar checks for close...
        
        return ValidationResult(
            rule_name="ohlc_consistency",
            passed=len(violations) == 0,
            failures=violations,
            severity="error"
        )

class PriceAnomalyRule(QualityRule):
    """Detect unrealistic price movements."""
    
    def __init__(self, max_single_bar_change: float = 0.20):
        self.max_change = max_single_bar_change
    
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        anomalies = []
        
        pct_change = data["close"].pct_change().abs()
        outliers = pct_change[pct_change > self.max_change]
        
        for idx in outliers.index:
            anomalies.append({
                "timestamp": idx,
                "pct_change": pct_change[idx],
                "threshold": self.max_change,
                "price_before": data.loc[idx]["close"],
                "price_after": data.loc[idx + 1]["close"] if idx + 1 in data.index else None
            })
        
        return ValidationResult(
            rule_name="price_anomaly",
            passed=len(anomalies) == 0,
            failures=anomalies,
            severity="warning"  # May be legitimate volatility
        )
```

### 2. Validation Pipeline

**Execution Flow:**
```
Data Ingestion
    ↓
Schema Validation (fast)
    ↓
Quality Rule Engine
    ↓
    ├─ Error Rules → Block ingestion
    ├─ Warning Rules → Log but accept
    └─ Info Rules → Record metrics
    ↓
Data Storage
```

**Configuration:**
```yaml
# config/quality_rules.yaml
rules:
  - name: temporal_continuity
    type: TemporalContinuityRule
    severity: error
    params:
      expected_interval: 1min
      tolerance: 1s
    enabled: true
    
  - name: ohlc_consistency
    type: OHLCConsistencyRule
    severity: error
    enabled: true
    
  - name: price_anomaly
    type: PriceAnomalyRule
    severity: warning
    params:
      max_single_bar_change: 0.20
    enabled: true
    
  - name: volume_validation
    type: VolumeValidationRule
    severity: warning
    params:
      min_volume: 0
    enabled: true
```

### 3. Quality Reporting

**Report Format:**
```json
{
  "report_id": "qr-2025-11-18-123456",
  "timestamp": "2025-11-18T10:30:00Z",
  "data_source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1min",
  "rows_evaluated": 1440,
  "overall_quality_score": 0.98,
  "rules_executed": 5,
  "rules_passed": 4,
  "rules_failed": 1,
  "results": [
    {
      "rule": "temporal_continuity",
      "severity": "error",
      "passed": false,
      "failures": [
        {
          "from": "2025-11-18T10:15:00Z",
          "to": "2025-11-18T10:18:00Z",
          "expected": "1min",
          "actual": "3min"
        }
      ]
    },
    {
      "rule": "ohlc_consistency",
      "severity": "error",
      "passed": true,
      "failures": []
    }
  ]
}
```

### 4. Integration Points

**Ingestion Pipeline:**
```python
from core.data.quality import QualityEngine, QualityReport

def ingest_market_data(data: pd.DataFrame, source: str) -> IngestionResult:
    # Run quality validation
    quality_engine = QualityEngine.from_config("config/quality_rules.yaml")
    report = quality_engine.validate(data)
    
    # Block on errors
    if report.has_errors():
        raise DataQualityError(
            f"Quality validation failed: {report.error_count} errors",
            report=report
        )
    
    # Log warnings
    if report.has_warnings():
        logger.warning(
            "Data quality warnings",
            extra={
                "report_id": report.report_id,
                "warning_count": report.warning_count
            }
        )
    
    # Store data with quality metadata
    version_id = store_versioned_data(data, quality_report=report)
    
    return IngestionResult(
        version_id=version_id,
        accepted_count=len(data),
        quality_score=report.overall_score
    )
```

### 5. Observability

**Metrics:**
- `data_quality_score` (gauge per symbol)
- `quality_rule_failures_total` (counter per rule)
- `ingestion_blocked_total` (counter per reason)
- `quality_validation_duration_seconds` (histogram)

**Dashboards:**
- Quality score trends over time
- Top failing symbols/exchanges
- Rule effectiveness (false positive rates)

## Consequences

### Positive
- **Early Detection:** Issues caught at ingestion, not during backtesting
- **Data Integrity:** High confidence in stored data quality
- **Debuggability:** Detailed reports enable quick root cause analysis
- **Configurability:** Rules can be enabled/disabled per asset class
- **Performance:** O(n) single-pass validation

### Negative
- **Ingestion Overhead:** ~5-10% latency increase for validation
- **False Positives:** Legitimate volatile events may be flagged
- **Configuration Complexity:** Need to tune thresholds per asset

### Neutral
- **Storage:** Quality reports add ~1KB per ingestion batch
- **Maintenance:** Rules need periodic review and adjustment

## Alternatives Considered

### Alternative 1: Statistical Process Control (SPC)
**Pros:**
- Adaptive thresholds based on historical data
- Fewer false positives over time

**Cons:**
- Requires warm-up period (cold start problem)
- Complex to implement and maintain
- Slower to detect novel anomalies

**Reason for rejection:** Rule-based approach simpler and sufficient for initial implementation. SPC can be added later for adaptive thresholds.

### Alternative 2: Machine Learning Anomaly Detection
**Pros:**
- Can detect subtle patterns
- Learns from data automatically

**Cons:**
- Requires labeled training data
- Black box (hard to explain failures)
- Higher latency and resource usage
- Risk of missing known patterns

**Reason for rejection:** Explainability critical for debugging. ML can augment rules but not replace them.

### Alternative 3: Manual Spot Checks
**Pros:**
- No implementation effort
- Human judgment can catch edge cases

**Cons:**
- Not scalable (millions of bars/day)
- Delayed detection (batch processing)
- Inconsistent application

**Reason for rejection:** Automation required for scale and consistency.

## Implementation

### Required Changes

1. **Core Framework** (`core/data/quality/`)
   - Implement base `QualityRule` class
   - Create 5+ standard rules (temporal, OHLC, volume, price anomaly, schema)
   - Build `QualityEngine` orchestrator
   - Implement reporting and visualization

2. **Configuration**
   - Define YAML schema for rule configuration
   - Create per-asset-class rule presets
   - Document rule parameters and tuning guidance

3. **Integration**
   - Hook validation into all ingestion pipelines
   - Add quality metadata to versioned storage
   - Implement metrics and alerting
   - Create quality dashboard

4. **Testing**
   - Unit tests for each rule with edge cases
   - Integration tests with known-bad data
   - Performance benchmarks (< 10% overhead target)
   - False positive rate measurement

### Migration Path

**Phase 1 (Month 1):** Core framework and basic rules
- Implement framework and 3 critical rules (temporal, OHLC, volume)
- Deploy in warning-only mode (log but don't block)
- Tune thresholds based on production data

**Phase 2 (Month 2):** Enforcement and expansion
- Enable blocking on critical errors
- Add remaining rules (price anomaly, schema, duplicates)
- Build quality dashboard and alerting

**Phase 3 (Month 3):** Optimization and advanced features
- Performance optimization (parallel rule execution)
- Add adaptive thresholds (SPC-based)
- Implement auto-remediation for common issues (forward-fill small gaps)

### Validation Criteria

1. **Functional Validation:**
   - All known data issues detected by appropriate rules
   - Zero false negatives on synthetic test dataset
   - False positive rate < 5% on production data

2. **Performance Validation:**
   - Validation overhead < 10% of ingestion latency
   - O(n) time complexity maintained
   - Memory usage < 2× data size

3. **Operational Validation:**
   - Quality dashboard provides actionable insights
   - 95% of blocked ingestions have clear remediation path
   - Mean time to resolution (MTTR) < 1 hour for quality issues

## Related Decisions
- ADR-0001: Fractal Indicator Composition (consumers need quality data)
- ADR-0002: Versioned Market Data Storage (quality metadata persisted with versions)
- REQ-002: Implements the automatic quality control requirement

## References
- [Data Quality Dimensions](https://en.wikipedia.org/wiki/Data_quality)
- [Great Expectations](https://greatexpectations.io/) - Similar framework for inspiration
- [Deequ](https://github.com/awslabs/deequ) - AWS data quality library
- REQ-002: Quality control requirement from docs/requirements/product_specification.md

## Notes

- Quality rules are versioned like features (backward compatibility)
- Rules can be asset-class specific (crypto vs. equities different thresholds)
- Quality reports retained for 90 days for analysis
- Critical for regulatory compliance (MiFID II data quality requirements)
- Framework designed to be extensible (custom rules easy to add)
