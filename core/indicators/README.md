---
owner: quant-systems@tradepulse
review_cadence: quarterly
last_reviewed: 2025-11-04
links:
  - ../../docs/indicators.md
  - ../../docs/architecture/system_modules_reference.md
  - ../../docs/documentation_standardisation_playbook.md
---

# Core Indicators Module

## Purpose

The `core/indicators` module provides advanced geometric and phase-synchrony indicators for algorithmic trading signal generation. This module implements cutting-edge mathematical techniques including Kuramoto oscillator analysis, Ricci flow curvature detection, multi-scale coherence analysis, and entropy-based market regime classification.

**Key Objectives:**
- Provide high-quality, deterministic market microstructure signals
- Enable multi-timeframe and multi-asset synchronization analysis
- Support both CPU and GPU-accelerated computation paths
- Deliver production-grade caching and feature persistence
- Maintain sub-100ms latency for real-time signal generation

## Key Responsibilities

- **Phase Synchronization Analysis**: Compute Kuramoto order parameters to detect collective market behavior and phase coherence across assets
- **Geometric Curvature Detection**: Apply Ricci flow and temporal curvature analysis to identify market regime transitions and topological shifts
- **Multi-Scale Feature Engineering**: Generate hierarchical features across multiple timeframes (5m, 15m, 1h, etc.) with wavelet-based window selection
- **Signal Composition**: Combine multiple indicators into unified composite signals with confidence scoring and risk calibration
- **Feature Caching**: Provide filesystem-based caching with fingerprinting for reproducible research and backtesting
- **GPU Acceleration**: Support CUDA/CuPy acceleration for computationally intensive operations on large datasets
- **Pipeline Orchestration**: Coordinate multi-stage indicator computation with dependency resolution and parallel execution

## Public Interfaces

| Interface | Type | Location | Description |
| --------- | ---- | -------- | ----------- |
| `KuramotoIndicator` | Class | `trading.py` | Production-ready Kuramoto order parameter calculator with configurable coupling strength |
| `HurstIndicator` | Class | `trading.py` | Hurst exponent estimator for detecting mean-reversion vs trending regimes |
| `VPINIndicator` | Class | `trading.py` | Volume-synchronized Probability of Informed Trading indicator |
| `TradePulseCompositeEngine` | Class | `kuramoto_ricci_composite.py` | Primary signal generator combining Kuramoto, Ricci, and topology analysis |
| `MultiScaleKuramoto` | Class | `multiscale_kuramoto.py` | Multi-timeframe Kuramoto analysis with consensus detection |
| `TemporalRicciAnalyzer` | Class | `temporal_ricci.py` | Temporal Ricci curvature flow analyzer for regime transitions |
| `IndicatorPipeline` | Class | `pipeline.py` | DAG-based orchestration for multi-indicator workflows |
| `FileSystemIndicatorCache` | Class | `cache.py` | Deterministic caching system with content-based fingerprinting |
| `compute_phase()` | Function | `kuramoto.py` | Convert price series to analytic signal phases via Hilbert transform |
| `compute_phase_gpu()` | Function | `kuramoto.py` | GPU-accelerated phase computation using CuPy |
| `kuramoto_order()` | Function | `kuramoto.py` | Calculate Kuramoto order parameter R from phase array |
| `compute_ensemble_divergence()` | Function | `ensemble_divergence.py` | Detect divergence between multiple indicator ensembles |
| `compute_hierarchical_features()` | Function | `hierarchical_features.py` | Generate multi-scale feature hierarchy with efficient buffering |

## Configuration

### Environment Variables:
- `TRADEPULSE_INDICATOR_CACHE_DIR`: Base directory for cached indicator results (default: `~/.tradepulse/cache/indicators`)
- `TRADEPULSE_USE_GPU`: Enable GPU acceleration when CuPy is available (default: `false`)
- `TRADEPULSE_INDICATOR_WORKERS`: Number of parallel workers for indicator computation (default: CPU count)

### Configuration Files:
Indicators are configured via Hydra YAML files in `configs/indicators/`:
- `kuramoto.yaml`: Kuramoto oscillator parameters (window, coupling, gpu_enabled)
- `ricci.yaml`: Ricci flow parameters (neighbor_k, curvature_threshold)
- `composite.yaml`: Composite engine thresholds and phase classification rules

### Feature Flags:
- `indicators.gpu_fallback`: Automatically fallback to CPU if GPU computation fails
- `indicators.cache_enabled`: Enable/disable filesystem caching layer
- `indicators.parallel_execution`: Enable parallel indicator computation in pipelines

## Dependencies

### Internal:
- `core.utils.logging`: Structured logging with correlation IDs
- `core.utils.metrics`: Prometheus metrics collector for observability
- `core.utils.cache`: Base caching primitives and utilities
- `core.data`: Data ingestion and quality control pipelines

### External Services/Libraries:
- **NumPy** (>=1.24): Core numerical operations and array processing
- **Pandas** (>=2.0): Time series data structures and alignment
- **SciPy** (>=1.11): Hilbert transform, signal processing utilities
- **CuPy** (optional, >=12.0): GPU-accelerated array operations (CUDA required)
- **Numba** (optional, >=0.57): JIT compilation for performance-critical loops

## Module Structure

```
core/indicators/
├── __init__.py                      # Public API exports
├── base.py                          # Base classes: BaseFeature, FeatureResult
├── cache.py                         # FileSystemIndicatorCache, fingerprinting
├── kuramoto.py                      # Phase synchronization, Kuramoto order
├── ricci.py                         # Static Ricci curvature computation
├── temporal_ricci.py                # Temporal Ricci flow analyzer
├── multiscale_kuramoto.py           # Multi-timeframe Kuramoto analysis
├── kuramoto_ricci_composite.py      # TradePulseCompositeEngine (main signal)
├── ensemble_divergence.py           # Multi-indicator divergence detection
├── hierarchical_features.py         # Multi-scale feature generation
├── pipeline.py                      # IndicatorPipeline orchestration
├── normalization.py                 # Indicator normalization utilities
├── pivot_detection.py               # Price pivot and divergence detection
├── entropy.py                       # Shannon/Rényi entropy measures
├── hurst.py                         # Hurst exponent estimation
└── trading.py                       # Production indicator wrappers
```

## Operational Notes

### SLIs / Metrics:
- `indicator_computation_duration_seconds{indicator, timeframe}`: Histogram of computation latency
- `indicator_cache_hit_ratio{indicator}`: Cache hit rate for reproducibility tracking
- `indicator_gpu_fallback_total{indicator}`: Counter for GPU computation failures
- `indicator_pipeline_stage_duration_seconds{stage}`: Pipeline stage breakdown
- `indicator_value_distribution{indicator, percentile}`: Summary of indicator values for monitoring distribution shifts

### Alarms:
- **High Latency**: Alert when P99 computation time exceeds 100ms for any indicator
- **Cache Miss Rate**: Alert when cache hit ratio drops below 60% during backtests
- **GPU Failures**: Alert on sustained GPU fallback rate > 10% over 5 minutes
- **NaN Values**: Alert on any NaN/Inf values in indicator outputs (data quality issue)

### Runbooks:
- [Indicator Performance Tuning](../../docs/performance.md#indicator-optimization)
- [GPU Troubleshooting](../../docs/troubleshooting.md#gpu-acceleration)
- [Cache Invalidation Guide](../../docs/operational_handbook.md#cache-management)

## Testing Strategy

### Unit Tests:
- **Test Coverage**: 92% (target: 95%)
- **Location**: `tests/core/test_indicators*.py`
- **Focus Areas**:
  - Mathematical correctness of Kuramoto order parameter
  - Numerical stability across edge cases (flat prices, NaN handling)
  - GPU/CPU parity validation for compute_phase_gpu
  - Cache fingerprinting uniqueness and determinism
  - Pipeline dependency resolution and error propagation

### Integration Tests:
- **Location**: `tests/integration/test_indicator_pipelines.py`
- **Scenarios**:
  - Multi-indicator pipeline execution with real market data
  - Cache persistence and restoration across process boundaries
  - GPU acceleration end-to-end with CuPy
  - Feature store integration for persisting hierarchical features

### End-to-End Tests:
- **Location**: `tests/e2e/test_backtest_with_indicators.py`
- **Validation**:
  - Full backtest using TradePulseCompositeEngine signals
  - Reproducibility check: same data + same config = identical signals
  - Performance benchmark: 10,000 bars processed in < 5 seconds

### Property-Based Tests:
- **Framework**: Hypothesis
- **Properties Validated**:
  - Kuramoto order R always in [0, 1]
  - Phase values always in [-π, π]
  - Cache retrieval matches fresh computation
  - Pipeline outputs deterministic for fixed inputs

## Usage Examples

### Basic Kuramoto Analysis
```python
from core.indicators import KuramotoIndicator
import numpy as np

# Create indicator instance
indicator = KuramotoIndicator(window=80, coupling=0.9)

# Compute on price series
prices = np.array([100, 101, 102, 101.5, 103, ...])
order_parameter = indicator.compute(prices)
print(f"Synchronization: {order_parameter:.3f}")  # 0.0 to 1.0
```

### Composite Signal Generation
```python
from core.indicators import TradePulseCompositeEngine
import pandas as pd

# Initialize composite engine
engine = TradePulseCompositeEngine()

# Prepare market data (OHLCV DataFrame)
bars = pd.DataFrame({
    'close': [...],
    'volume': [...]
}, index=pd.DatetimeIndex([...]))

# Generate composite signal
signal = engine.analyze_market(bars)

print(f"Phase: {signal.phase.value}")
print(f"Confidence: {signal.confidence:.3f}")
print(f"Entry Signal: {signal.entry_signal:.3f}")
print(f"Risk Multiplier: {signal.risk_multiplier:.2f}")
```

### Multi-Scale Analysis
```python
from core.indicators import MultiScaleKuramoto, TimeFrame

# Define timeframes
timeframes = [
    TimeFrame(name="5m", window_bars=60, timeframe_sec=300),
    TimeFrame(name="15m", window_bars=60, timeframe_sec=900),
    TimeFrame(name="1h", window_bars=60, timeframe_sec=3600),
]

# Create multi-scale analyzer
analyzer = MultiScaleKuramoto(timeframes=timeframes)

# Analyze across scales
result = analyzer.compute(prices)
print(f"Consensus R: {result.consensus_R:.3f}")
print(f"Dominant Scale: {result.dominant_timeframe_sec}s")
```

### Pipeline Orchestration
```python
from core.indicators import IndicatorPipeline

# Define pipeline DAG
pipeline = IndicatorPipeline([
    ('kuramoto', KuramotoIndicator(window=80)),
    ('hurst', HurstIndicator(window=100)),
    ('vpin', VPINIndicator(window=50)),
])

# Execute pipeline on data
results = pipeline.compute(bars)
for name, value in results.features.items():
    print(f"{name}: {value:.4f}")
```

### Caching for Reproducibility
```python
from core.indicators import cache_indicator, KuramotoIndicator

# Wrap indicator with caching
cached_indicator = cache_indicator(
    KuramotoIndicator(window=80),
    cache_dir="./cache/backtest_v1"
)

# First call computes and caches
result1 = cached_indicator.compute(prices)

# Second call retrieves from cache (instant)
result2 = cached_indicator.compute(prices)
assert np.allclose(result1, result2)
```

## Performance Characteristics

### Computational Complexity:
- **Kuramoto Order**: O(n) for n-length price series
- **Hilbert Transform**: O(n log n) via FFT
- **Multi-Scale Analysis**: O(k × n) for k timeframes
- **Ricci Curvature**: O(n × k²) for k-nearest neighbors
- **Composite Engine**: O(n log n) dominated by FFT operations

### Memory Requirements:
- **Per-indicator baseline**: ~10 MB (class initialization)
- **Per-computation**: ~1 MB per 10,000 bars
- **Cache storage**: ~100 KB per cached indicator result (compressed)
- **GPU memory**: 100-500 MB for large dataset batches (CuPy)

### Latency Targets:
- Single indicator on 1,000 bars: < 10ms (CPU), < 5ms (GPU)
- Composite engine on 5,000 bars: < 50ms
- Full pipeline (5 indicators) on 10,000 bars: < 200ms

## Changelog

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-11-04 | docs@tradepulse | Created comprehensive README following standardization playbook |

## See Also

- [Indicator Library Documentation](../../docs/indicators.md)
- [System Modules Reference](../../docs/architecture/system_modules_reference.md)
- [Performance Testing Program](../../docs/performance_testing_program.md)
- [Quality Gates](../../docs/quality_gates.md)
