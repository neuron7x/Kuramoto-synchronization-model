# TradePulse-QLW v1.1.0 — Technical Documentation

## Overview

TradePulse-QLW is a physics-based liquidity and order execution risk model that interprets market dynamics as a damped stochastic wave with absorbing boundaries (PML). The system combines:

- **PDE Solver**: Newmark-β integration for damped wave equations
- **MF-DFA Calibration**: Multifractal Detrended Fluctuation Analysis for Hurst exponent estimation
- **PID-Tau Controller**: Adaptive threshold management with anti-windup
- **TACL Integration**: Thermodynamic Autonomic Control Layer for gate decisions
- **FastAPI Service**: Production-ready API with rate limiting and audit

## Quick Start

### Installation

```bash
pip install -e .
```

### Basic Usage

```python
import numpy as np
from src.tradepulse_qlw import QLWConfig, QLWEngine

# Configure engine
cfg = QLWConfig(nx=128, nt=512, seed=42)
engine = QLWEngine(cfg)

# Generate synthetic market features
features = np.random.normal(1.0, 0.1, (512, 40))

# Run analysis
result = engine.run(features)

print(f"Gamma: {result.meta['gamma']:.3f}")
print(f"Tau: {result.meta['tau']:.3f}")
print(f"Forbidden ratio: {result.forbidden_mask.mean():.3f}")
```

### API Server

```bash
uvicorn src.tradepulse_qlw.api:app --host 0.0.0.0 --port 8000
```

Then POST to `/v1/solve`:

```json
{
  "features_fmn": [[1.0, 1.1, ...], ...],
  "orderbook": [[[100, 50], ...], ...],
  "cfg": {
    "nx": 128,
    "nt": 512,
    "forbidden_mode": "quantile"
  }
}
```

## Architecture

### Core Components

1. **PDE Solver** (`pde_solver.py`)
   - Newmark-β time integration (β=0.25, γ=0.5)
   - PML absorbing boundaries
   - Optional Numba/GPU acceleration

2. **MF-DFA Module** (`mdfa.py`)
   - Hurst exponent estimation
   - Gamma calibration from H
   - Multi-scale analysis

3. **Risk Controller** (`risk/adaptive_tau.py`)
   - PID control loop
   - Anti-windup protection
   - Threshold adaptation

4. **Engine** (`engine.py`)
   - Wave speed computation from order flow
   - Phase alignment analysis
   - Forbidden zone detection
   - TACL gate triggers

### Configuration

See `configs/profiles/balanced.yml` for a production-ready profile.

Key parameters:
- `nx`, `nt`: Spatial and temporal grid sizes
- `gamma_lo`, `gamma_hi`: Damping coefficient bounds
- `c_min`, `c_max`: Wave speed bounds
- `pml_width_frac`, `pml_gain`: PML parameters
- `forbidden_mode`: Threshold computation mode (static/quantile/mad/pid)

## Mathematical Foundation

### Damped Wave PDE

```
∂²ψ/∂t² = c²∂²ψ/∂x² - Γ(x)ψ + η(t,x)
```

where:
- `ψ`: Wave field
- `c`: Wave speed (calibrated from order flow)
- `Γ(x)`: Damping profile with PML
- `η`: Stochastic forcing

### MF-DFA Calibration

Window-based Hurst estimation:
```
H = d(log F_q) / d(log s)
```

Map to damping:
```
γ = γ_lo + (γ_hi - γ_lo)(1 - H)
```

### PID-Tau Control

```
e = target - current_ratio
τ_new = τ + Kp·e + Ki·∫e + Kd·de/dt
```

with integrator clamping for anti-windup.

## Testing

Run tests:
```bash
pytest tests/qlw/ -v
```

Key test suites:
- `test_energy_long.py`: Energy monotonicity
- `test_calibration.py`: MF-DFA and gamma bounds
- `test_pid_tau.py`: PID controller behavior
- `test_engine.py`: End-to-end integration
- `test_config.py`: Configuration validation

## Benchmarks

### Reflection Benchmark

```bash
python scripts/qlw/reflection_benchmark.py
```

Measures PML effectiveness at different gains and widths.

### Live Streaming

```bash
python scripts/qlw/stream_binance_spot.py
```

Connects to Binance WebSocket and runs real-time analysis.

## Monitoring

### Prometheus Metrics

- `qlw_phase_rmse`: Phase alignment error
- `qlw_forbidden_tau`: Adaptive threshold
- `qlw_energy_mean`: Average wave energy
- `solver_ms_per_step`: Solver latency
- `qlw_hard_gate_total`: Hard gate triggers

### Grafana Dashboard

See `configs/grafana/dashboard.json` for visualization.

### Alerts

Configured in `configs/prometheus/rules.yml`:
- Phase RMSE elevation
- Queue drops
- Forbidden zone surge
- Latency degradation

## Deployment

### Docker

```bash
docker build -t tradepulse-qlw:1.1.0 .
docker run -p 8000:8000 tradepulse-qlw:1.1.0
```

### Kubernetes/Helm

```bash
helm upgrade --install qlw charts/qlw
```

Includes:
- HPA (3-15 replicas, CPU target 60%)
- PDB (min 2 available)
- ServiceMonitor for Prometheus
- NetworkPolicy for security

### Argo Rollouts

Progressive canary deployment with analysis:
```yaml
steps:
  - setWeight: 5
  - pause: {duration: 300}
  - analysis: {templates: [qlw-analysis]}
  - setWeight: 25
  - setWeight: 100
```

## Security

- **PSS**: Restricted pod security
- **Non-root**: User 1000, fsGroup 2000
- **Read-only root**: Prevents tampering
- **Rate limiting**: 20 req/s per IP
- **Audit headers**: SHA256 request hash
- **PII masking**: Logs hash payloads

## Performance

Typical latencies (balanced profile):
- Solve time: 50-200ms (128×512 grid)
- P95 latency: <1.0ms per timestep
- Memory: ~256MB baseline, ~2GB peak

Optimization:
- Enable `use_numba: true` for 5-10x speedup
- GPU acceleration via `use_gpu: true` (requires CuPy)
- Adjust grid sizes for accuracy/speed tradeoff

## References

1. Newmark-β time integration
2. Perfectly Matched Layer (PML) boundaries
3. Multifractal DFA for Hurst exponent
4. PID control theory
5. Thermodynamic Autonomic Control Layer (TACL)

## License

MIT (code) · CC-BY-4.0 (docs)

## Contributing

See main repository CONTRIBUTING.md for guidelines.
