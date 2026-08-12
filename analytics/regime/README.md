---
owner: quant-research@geosync
review_cadence: quarterly
last_reviewed: 2025-11-04
links:
  - ../../docs/architecture/system_modules_reference.md
  - ../../docs/indicators.md
---

# Analytics Regime Module

## Purpose

The `analytics/regime` module provides **multi-dimensional market regime detection** across trend, volatility, liquidity, and correlation axes. Unlike the FPMA module which uses probabilistic state models, this module employs robust statistical measures and interpretable heuristics for real-time regime classification. Analogous to how sensory systems integrate multiple modalities (vision, sound, touch) to understand environmental context, this module fuses multiple market signals to infer trading conditions.

**Neuroeconomic Mapping:**
- **Multisensory Integration (Parietal Cortex)**: Combine trend, volatility, liquidity, correlation signals into unified regime
- **Pattern Recognition (Temporal Cortex)**: Identify recurring market patterns (trending vs mean-reverting)
- **Context Encoding (Hippocampus)**: Maintain regime history for temporal context
- **Causal Inference (Prefrontal Cortex)**: Distinguish causal regime drivers from noise
- **Early Warning (Anterior Insula)**: Detect subtle regime shifts before full transition

**Key Objectives:**
- Provide real-time regime classification with < 1-second latency
- Support multiple time horizons (intraday, daily, weekly) simultaneously
- Maintain interpretability with human-readable regime labels and diagnostics
- Enable regime-aware strategy adjustments (risk scaling, execution style)
- Detect early warning signals of regime transitions (EWS module)

## Key Responsibilities

- **Trend Regime Detection**: Classify as TRENDING, MEAN_REVERTING, or RANGING based on autocorrelation and directional strength
- **Volatility Regime Assessment**: Categorize as LOW, NORMAL, or HIGH volatility environment
- **Liquidity Regime Analysis**: Evaluate market liquidity as LOW, MODERATE, or HIGH
- **Correlation Regime Tracking**: Measure cross-asset correlation as DECOUPLED, MIXED, or COUPLED
- **Regime Fusion**: Combine individual regime dimensions into unified market state
- **Strategy Adjustment Recommendations**: Suggest risk multipliers, position sizing, and execution tactics
- **Early Warning System (EWS)**: Detect pre-transition signals using critical slowing down indicators
- **Topological Analysis**: Monitor market topology changes via Ricci flow and Kuramoto synchronization
- **Causal Guards**: Filter spurious regime signals to prevent false positives

## Public Interfaces

| Interface | Type | Location | Description |
| --------- | ---- | -------- | ----------- |
| `RegimeDetector` | Class | `core/main.py` | Main multi-dimensional regime detection engine |
| `MarketRegimeSnapshot` | Dataclass | `core/main.py` | Regime state with diagnostics and adjustments |
| `TrendRegime` | Enum | `core/main.py` | Trend classification: TRENDING, MEAN_REVERTING, RANGING |
| `VolatilityRegime` | Enum | `core/main.py` | Volatility level: LOW, NORMAL, HIGH |
| `LiquidityRegime` | Enum | `core/main.py` | Liquidity condition: LOW, MODERATE, HIGH |
| `CorrelationRegime` | Enum | `core/main.py` | Cross-asset correlation: DECOUPLED, MIXED, COUPLED |
| `EarlyWarningSystem` | Class | `core/ews.py` | Early warning signals for regime transitions |
| `RicciFlowAnalyzer` | Class | `core/ricci_flow.py` | Topological regime analysis via Ricci curvature |
| `TopologicalSentinel` | Class | `core/topo_sentinel.py` | Monitor topology changes for structural breaks |
| `CausalGuard` | Class | `core/causal_guard.py` | Filter spurious regime signals |
| `ForemanKahaneDetector` | Class | `core/fk_detector.py` | Foreman-Kahane volatility clustering detection |

## Configuration

### Environment Variables:
- `GEOSYNC_REGIME_LOOKBACK_BARS`: Bars for regime calculation (default: `64`)
- `GEOSYNC_REGIME_UPDATE_FREQUENCY`: Update frequency in seconds (default: `60`)
- `GEOSYNC_ENABLE_EWS`: Enable early warning system (default: `true`)
- `GEOSYNC_ENABLE_TOPO_SENTINEL`: Enable topological monitoring (default: `true`)

### Configuration Files:
Regime detection is configured via `configs/analytics/regime/`:
- `detector.yaml`: Trend, volatility, liquidity, correlation thresholds
- `ews.yaml`: Early warning signal parameters
- `ricci.yaml`: Ricci flow analyzer configuration
- `adjustments.yaml`: Regime-specific strategy adjustment templates

### Feature Flags:
- `regime.enable_trend_detection`: Trend regime classification
- `regime.enable_volatility_detection`: Volatility regime assessment
- `regime.enable_liquidity_detection`: Liquidity regime analysis
- `regime.enable_correlation_detection`: Correlation regime tracking
- `regime.enable_ews`: Early warning signals
- `regime.enable_causal_guards`: Causal filtering of regime signals

## Dependencies

### Internal:
- `core.indicators`: Kuramoto, Ricci flow, Hurst exponent indicators
- `core.data`: Market data access for regime calculation
- `core.utils.logging`: Structured logging for regime transitions
- `core.utils.metrics`: Regime detection metrics

### External Services/Libraries:
- **NumPy** (>=1.24): Numerical operations
- **Pandas** (>=2.0): Time series manipulation
- **Scikit-learn** (>=1.3): Statistical analysis, correlation matrices
- **SciPy** (>=1.11): Signal processing, statistical tests

## Module Structure

```
analytics/regime/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── main.py                  # RegimeDetector
│   │   ├── ews.py                   # Early Warning System
│   │   ├── ricci_flow.py            # Ricci curvature analysis
│   │   ├── topo_sentinel.py         # Topological monitoring
│   │   ├── causal_guard.py          # Causal signal filtering
│   │   ├── fk_detector.py           # Foreman-Kahane detector
│   │   ├── geosync_v21.py        # GeoSync v2.1 integration
│   │   └── _sklearn_compat.py       # Scikit-learn compatibility
│   ├── ports/
│   │   ├── __init__.py
│   │   └── ports.py                 # Protocol interfaces
│   ├── adapters/
│   │   ├── __init__.py
│   │   └── local.py                 # Local adapter
│   └── consensus/
│       ├── __init__.py
│       └── hncm_adapter.py          # Hierarchical consensus adapter
└── tests/
    ├── test_core.py
    ├── test_ricci_flow.py
    ├── test_hncm_consensus.py
    └── test_geosync_v21.py
```

## Regime Dimensions

### 1. Trend Regime
**TRENDING**: Strong directional movement
- High absolute momentum (z-score > 1.0)
- Positive autocorrelation at lag 1
- Persistent price direction over trend_window

**MEAN_REVERTING**: Price oscillation around mean
- Negative autocorrelation (< -0.05)
- High reversion speed
- Bollinger Band reversals

**RANGING**: Sideways, choppy price action
- Low momentum z-score (< 1.0)
- Near-zero autocorrelation
- Price confined to narrow range

### 2. Volatility Regime
**LOW**: Calm market conditions
- Realized volatility < 0.5 × historical median
- Tight Bollinger Bands
- Low ATR (Average True Range)

**NORMAL**: Typical volatility levels
- Realized volatility near historical median
- Standard Bollinger Band width

**HIGH**: Elevated volatility
- Realized volatility > 2.0 × historical median
- Wide Bollinger Bands
- High ATR

### 3. Liquidity Regime
**LOW**: Thin markets, wide spreads
- High bid-ask spread (> 2× normal)
- Low volume (< 0.5× average)
- Irregular order flow

**MODERATE**: Typical liquidity
- Normal spreads and volume
- Consistent order flow

**HIGH**: Deep, liquid markets
- Tight spreads (< 0.5× normal)
- High volume (> 2× average)
- Dense order book

### 4. Correlation Regime
**DECOUPLED**: Assets move independently
- Cross-asset correlation < 0.25
- Diversification benefits high

**MIXED**: Moderate correlation
- Correlation in 0.25-0.6 range
- Some diversification remains

**COUPLED**: Assets move together
- Correlation > 0.6
- Reduced diversification (risk-off)

## Neuroeconomic Principles

### Multisensory Integration (Parietal Cortex)
Like the brain integrates visual, auditory, and tactile signals to form coherent perception, regime detector fuses multiple market dimensions:

```python
regime_snapshot = RegimeDetector.detect(
    prices=prices,
    volumes=volumes,
    spreads=spreads,
    correlations=correlations,
)

# Unified regime representation from multiple signals
regime_state = {
    "trend": regime_snapshot.trend,          # "TRENDING"
    "volatility": regime_snapshot.volatility,  # "HIGH"
    "liquidity": regime_snapshot.liquidity,    # "MODERATE"
    "correlation": regime_snapshot.correlation,  # "COUPLED"
}
```

### Predictive Coding (Early Warning System)
EWS implements prediction error detection for regime transitions:

```python
# Measure "critical slowing down" before regime shift
ews_signals = early_warning_system.analyze(prices)

if ews_signals["autocorrelation_increase"] and ews_signals["variance_increase"]:
    # System losing resilience → regime transition imminent
    alert_regime_change()
```

This mirrors how the brain detects contextual violations before conscious awareness.

### Causal Inference (Prefrontal Cortex)
CausalGuard filters spurious correlations:

```python
# Don't confuse noise with regime change
if causal_guard.is_spurious(regime_signal):
    # Likely random fluctuation, not true regime shift
    ignore_signal()
else:
    # Statistically significant regime change
    act_on_signal()
```

### Topological Invariance (Hippocampal Place Cells)
Topological features (Ricci curvature, Kuramoto sync) capture structural market properties robust to noise:

```python
# Topology changes indicate fundamental regime shift
ricci_curvature = ricci_analyzer.compute_curvature(correlation_matrix)

if ricci_curvature < -0.3:
    # Network topology strained → high crash risk
    regime = "TURBULENT_BEAR"
```

## Operational Notes

### SLIs / Metrics:
- `regime_detection_latency_seconds`: Time to classify regime
- `regime_current{dimension, label}`: Active regime per dimension
- `regime_transition_total{from, to, dimension}`: Transition count
- `regime_confidence{dimension}`: Classification confidence (0-1)
- `ews_signal_strength`: Early warning signal intensity
- `topo_curvature_mean`: Average Ricci curvature
- `regime_diagnostics{metric}`: Diagnostic values (autocorr, vol, etc.)

### Alarms:
- **High: EWS Critical Signals**: Multiple EWS indicators active
- **High: Topology Breakdown**: Ricci curvature < -0.5
- **Medium: Rapid Regime Switching**: > 3 transitions in 1 hour
- **Medium: Correlation Surge**: Correlation regime → COUPLED
- **Low: Regime Uncertainty**: Low confidence across dimensions

### Runbooks:
- [Regime Interpretation Guide](../../docs/indicators.md#regime-indicators)
- [EWS Response Procedures](../../docs/operational_handbook.md#ews-alerts)
- [Topological Alert Handling](../../docs/operational_handbook.md#topology-alerts)

## Testing Strategy

### Unit Tests:
- **Test Coverage**: 89% (target: 90%)
- **Location**: `analytics/regime/tests/test_core.py`
- **Focus Areas**:
  - Regime classification accuracy on synthetic data
  - EWS sensitivity and specificity
  - Ricci flow numerical stability
  - Causal guard false positive rate

### Integration Tests:
- **Location**: `tests/integration/test_regime_detection.py`
- **Scenarios**:
  - Multi-timeframe regime detection
  - Regime-aware strategy integration
  - EWS → regime transition validation

### Backtesting:
- **Framework**: Event-driven backtest
- **Validation**:
  - Regime-aware vs regime-blind strategies
  - EWS lead time accuracy (transition prediction)
  - Topology-based risk indicators

## Usage Examples

### Basic Regime Detection
```python
from analytics.regime import RegimeDetector, DetectorConfig

# Configure detector
config = DetectorConfig(
    trend_window=48,
    volatility_window=64,
    liquidity_window=64,
    correlation_window=64,
)

detector = RegimeDetector(config)

# Detect regime
snapshot = detector.detect_regime(
    prices=prices,
    volumes=volumes,
    returns=returns,
    correlations=correlation_matrix,
)

print(f"Trend: {snapshot.trend}")
print(f"Volatility: {snapshot.volatility}")
print(f"Liquidity: {snapshot.liquidity}")
print(f"Correlation: {snapshot.correlation}")
print(f"\nDiagnostics:")
for key, value in snapshot.diagnostics.items():
    print(f"  {key}: {value:.3f}")
```

### Strategy Adjustments
```python
from analytics.regime import RegimeDetector

detector = RegimeDetector()
snapshot = detector.detect_regime(prices, volumes, returns, correlations)

# Get regime-specific adjustments
adjustments = snapshot.adjustments

# Apply adjustments to strategy
risk_multiplier = adjustments.risk_multiplier
position_scale = adjustments.position_scale
execution_style = adjustments.execution_style

print(f"Risk Multiplier: {risk_multiplier}x")
print(f"Position Scale: {position_scale}x")
print(f"Execution Style: {execution_style}")
print(f"Parameter Overrides: {adjustments.parameter_overrides}")
print(f"Notes: {adjustments.notes}")

# Example: Scale position size based on regime
base_position_size = 100
actual_position_size = base_position_size * position_scale * risk_multiplier
```

### Early Warning System
```python
from analytics.regime import EarlyWarningSystem

ews = EarlyWarningSystem(
    window_size=100,
    warning_threshold=2.0,  # Standard deviations
)

# Monitor for regime transition signals
ews_signals = ews.analyze(prices)

if ews_signals["critical_slowing_down"]:
    print("⚠️ Critical slowing down detected")
    print(f"  Autocorrelation: {ews_signals['autocorr']:.3f} (↑ from {ews_signals['autocorr_baseline']:.3f})")
    print(f"  Variance: {ews_signals['variance']:.3f} (↑ from {ews_signals['variance_baseline']:.3f})")
    print(f"  Skewness: {ews_signals['skewness']:.3f}")
    print("  → Regime transition likely within 1-5 days")
```

### Topological Analysis
```python
from analytics.regime import RicciFlowAnalyzer

ricci_analyzer = RicciFlowAnalyzer()

# Compute market topology
ricci_curvature = ricci_analyzer.compute_curvature(
    correlation_matrix=correlation_matrix,
    prices=prices,
)

print(f"Average Ricci Curvature: {ricci_curvature:.3f}")

if ricci_curvature < -0.3:
    print("⚠️ Negative curvature → Market stress")
    print("  → Correlation structure strained")
    print("  → Crash risk elevated")
elif ricci_curvature > 0.2:
    print("✓ Positive curvature → Market stability")
    print("  → Healthy correlation structure")
```

### Multi-Dimensional Regime Monitoring
```python
from analytics.regime import RegimeDetector
import time

detector = RegimeDetector()

# Continuous regime monitoring loop
while trading_active:
    snapshot = detector.detect_regime(
        prices=get_recent_prices(),
        volumes=get_recent_volumes(),
        returns=get_recent_returns(),
        correlations=get_correlation_matrix(),
    )
    
    # Log regime state
    logger.info(
        "Regime Update",
        trend=snapshot.trend.value,
        volatility=snapshot.volatility.value,
        liquidity=snapshot.liquidity.value,
        correlation=snapshot.correlation.value,
        diagnostics=snapshot.diagnostics,
    )
    
    # Check for regime changes
    if snapshot.trend != previous_snapshot.trend:
        logger.warning(
            "Trend Regime Change",
            from_regime=previous_snapshot.trend.value,
            to_regime=snapshot.trend.value,
        )
    
    # Apply adjustments
    update_strategy_parameters(snapshot.adjustments)
    
    previous_snapshot = snapshot
    time.sleep(60)  # Update every minute
```

### Causal Regime Validation
```python
from analytics.regime import RegimeDetector, CausalGuard

detector = RegimeDetector()
causal_guard = CausalGuard(significance_level=0.05)

snapshot = detector.detect_regime(prices, volumes, returns, correlations)

# Validate regime signal is not spurious
is_valid = causal_guard.validate_regime_signal(
    current_regime=snapshot,
    historical_regimes=regime_history,
    market_data=prices,
)

if is_valid:
    print("✓ Regime signal validated (statistically significant)")
    act_on_regime(snapshot)
else:
    print("⚠️ Regime signal rejected (likely spurious)")
    # Wait for stronger evidence
```

## Performance Characteristics

### Latency:
- Single regime detection: 50-200ms
- Multi-timeframe detection: 200-500ms
- EWS analysis: 100-300ms
- Ricci flow computation: 300-800ms (depends on matrix size)

### Accuracy (Offline Validation):
- Trend regime: 85-90% accuracy
- Volatility regime: 90-95% accuracy
- Liquidity regime: 80-85% accuracy
- Correlation regime: 85-90% accuracy

### Memory:
- Detector instance: ~5 MB
- EWS buffers: ~2 MB per timeframe
- Ricci analyzer: ~10 MB

### Scalability:
- Supports 100+ symbols simultaneously
- Handles tick-to-daily frequencies
- Parallel detection across timeframes

## Changelog

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-11-04 | quant-research@geosync | Created comprehensive README with multisensory integration principles |

## See Also

- [System Modules Reference](../../docs/architecture/system_modules_reference.md)
- [Indicator Library](../../docs/indicators.md)
- [Operational Handbook: Regime Monitoring](../../docs/operational_handbook.md#regime-monitoring)
- [Neuroeconomic Principles](../../docs/neuroecon.md)
