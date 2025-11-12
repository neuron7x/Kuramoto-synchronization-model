# TradePulse-QLW v1.1.0

**Quantum-like Wave Model for Liquidity and Execution Risk**

## Overview

TradePulse-QLW is a physics-based model that interprets market liquidity and execution risk as a damped stochastic wave with absorbing boundaries. It combines:

- **Partial Differential Equations (PDE)**: Damped wave equation with Perfectly Matched Layer (PML)
- **Multifractal Analysis**: MF-DFA for Hurst exponent estimation and damping calibration
- **Adaptive Control**: PID-Tau controller with anti-windup for threshold management
- **Thermodynamic Autonomic Control Layer (TACL)**: Gate decisions based on energy metrics
- **Production API**: FastAPI service with rate limiting, audit logging, and Prometheus metrics

## Key Features

### 1. Physical Market Modeling
- Models market dynamics as wave propagation
- Calibrates wave speed from order flow pressure
- Damping coefficient derived from multifractal analysis
- PML boundaries for reflection suppression

### 2. Risk Detection
- **Forbidden Zones**: Identifies high-risk regions in the wave field
- **Adaptive Thresholds**: PID controller maintains target forbidden ratio
- **Soft/Hard Gates**: Progressive penalty system for TACL integration
- **Phase Alignment**: Resonance analysis with price dynamics

### 3. Production Ready
- FastAPI service with health checks
- Rate limiting (20 req/s per IP)
- Structured audit logging with SHA256 hashing
- Prometheus metrics and Grafana dashboards
- Kubernetes/Helm deployment with HPA
- Argo Rollouts for progressive canary deployment

## Quick Start

### Installation

```bash
# From repository root
pip install -e .
```

### Basic Usage

```python
import numpy as np
from src.tradepulse_qlw import QLWConfig, QLWEngine

# Configure
cfg = QLWConfig(
    nx=128,           # Spatial grid points
    nt=512,           # Time steps
    forbidden_mode="quantile",  # Threshold computation
    seed=42
)

# Initialize engine
engine = QLWEngine(cfg)

# Generate synthetic market features (nt × n_features)
features = np.random.normal(1.0, 0.1, (512, 40))

# Run analysis
result = engine.run(features)

# Access results
print(f"Damping coefficient: {result.meta['gamma']:.3f}")
print(f"Adaptive threshold: {result.meta['tau']:.3f}")
print(f"Forbidden ratio: {result.forbidden_mask.mean():.2%}")
print(f"Phase alignment AUC: {result.meta['R_auc']:.3f}")

# Wave field shape: (nt, nx)
print(f"Wave field shape: {result.psi.shape}")
```

### With Order Book Data

```python
# Order book shape: (nt, depth, 2) for [bid_levels, ask_levels]
orderbook = np.random.uniform(0.5, 1.5, (512, 10, 2))

result = engine.run(features, orderbook=orderbook)
```

### API Server

```bash
# Start server
uvicorn src.tradepulse_qlw.api:app --host 0.0.0.0 --port 8000

# Check health
curl http://localhost:8000/healthz

# Solve
curl -X POST http://localhost:8000/v1/solve \
  -H "Content-Type: application/json" \
  -d '{
    "features_fmn": [[1.0, 1.1, ...], ...],
    "cfg": {
      "nx": 128,
      "nt": 512,
      "forbidden_mode": "pid"
    }
  }'

# Prometheus metrics
curl http://localhost:8000/metrics
```

## Architecture

### Core Modules

```
src/tradepulse_qlw/
├── __init__.py          # Package exports
├── config.py            # Configuration (Pydantic)
├── types.py             # Data types
├── pde_solver.py        # Newmark-β PDE solver
├── mdfa.py              # MF-DFA and Hurst estimation
├── engine.py            # Main QLW engine
├── api.py               # FastAPI service
├── logging_setup.py     # Logging with PII masking
└── risk/
    ├── __init__.py
    └── adaptive_tau.py  # PID-Tau controller
```

### Configuration Profiles

```yaml
# configs/profiles/balanced.yml
nx: 128
nt: 512
dx: 1.0
dt: 0.02
forbidden_mode: quantile
gamma_lo: 0.05
gamma_hi: 0.6
pml_gain: 2.0
pid_target: 0.15
```

## Mathematical Foundation

### Damped Wave PDE

```
∂²ψ/∂t² = c²∂²ψ/∂x² - Γ(x)ψ + η(t,x)
```

where:
- `ψ(t,x)`: Wave field
- `c`: Wave speed (calibrated from order flow)
- `Γ(x) = γ + g·ρ(x)`: Damping with PML profile
- `η`: Gaussian noise

### Newmark-β Integration

```
u_{n+1} = u_n + Δt·v_n + (1/2 - β)Δt²·a_n + β·Δt²·a_{n+1}
v_{n+1} = v_n + (1 - γ)Δt·a_n + γ·Δt·a_{n+1}
```

with β=0.25, γ=0.5 for unconditional stability.

### MF-DFA Calibration

1. Compute cumulative profile: `Y(i) = Σ(x_k - x̄)`
2. Segment into windows of scale s
3. Detrend each segment (linear fit)
4. Compute fluctuation: `F_q(s) = [⟨|Y_detrended|^q⟩]^(1/q)`
5. Estimate Hurst: `H = d(log F_q) / d(log s)`
6. Map to damping: `γ = γ_lo + (γ_hi - γ_lo)(1 - H)`

### PID-Tau Control

```
e = target - current_ratio
I = clip(I + e, -10, 10)  # Anti-windup
D = e - e_prev
τ_new = clip(τ + Kp·e + Ki·I + Kd·D, τ_min, τ_max)
```

## Testing

```bash
# Run all tests
pytest tests/qlw/ -v

# Run specific test suite
pytest tests/qlw/test_energy_long.py -v

# With coverage
pytest tests/qlw/ --cov=src/tradepulse_qlw --cov-report=html
```

Test suites:
- `test_energy_long.py`: Energy decay, PML effectiveness
- `test_calibration.py`: MF-DFA, gamma bounds, stability
- `test_pid_tau.py`: PID controller, anti-windup, convergence
- `test_engine.py`: End-to-end integration, all modes
- `test_config.py`: Configuration validation

## Benchmarks

### Reflection Benchmark

```bash
python scripts/qlw/reflection_benchmark.py
```

Measures edge energy reflection ratio for different PML configurations:
- No PML: ρ ≈ 0.05
- gain=2.0, width=0.075: ρ ≈ 0.021
- gain=4.0, width=0.1: ρ ≈ 0.009

### Live Market Streaming

```bash
python scripts/qlw/stream_binance_spot.py
```

Connects to Binance WebSocket, runs real-time QLW analysis, logs metrics to CSV.

## Deployment

### Docker

```bash
docker build -f Dockerfile.qlw -t tradepulse-qlw:1.1.0 .
docker run -p 8000:8000 tradepulse-qlw:1.1.0
```

### Kubernetes/Helm

```bash
helm install qlw charts/qlw \
  --set image.tag=1.1.0 \
  --set autoscaling.minReplicas=3 \
  --set autoscaling.maxReplicas=15
```

### Argo Rollouts

```bash
kubectl apply -f deploy/argo/rollout.yaml
kubectl apply -f deploy/argo/istio-virtualservice.yaml

# Monitor rollout
kubectl argo rollouts get rollout tradepulse-qlw -w
```

## Monitoring

### Prometheus Metrics

Key metrics exposed at `/metrics`:
- `qlw_phase_rmse`: Phase alignment RMSE
- `qlw_forbidden_tau`: Adaptive threshold
- `qlw_energy_mean`: Average wave energy
- `solver_ms_per_step`: Solver latency (histogram)
- `qlw_hard_gate_total`: Hard gate triggers (counter)

### Grafana Dashboard

Import `configs/grafana/dashboard.json` for:
- Stability metrics (energy, phase RMSE)
- Risk envelope (tau, forbidden ratios)
- Solver performance (p95, p99 latency)
- Gate triggers (hard/soft)

### Alerts

Configured in `configs/prometheus/rules.yml`:
- `QLWPhaseRMSEHigh`: Phase RMSE >15% above baseline
- `QLWQueueDrops`: Ingress queue overflow
- `QLWForbiddenSurge`: Tau spike >30% vs 1h avg
- `QLWSolverLatencyHigh`: p95 latency >1.0ms

## Performance

Typical performance (balanced profile, 128×512 grid):
- Solve time: 50-200ms
- P95 latency: <1.0ms per timestep
- Memory: ~256MB baseline, ~2GB peak
- Throughput: 5-20 solves/sec (depending on grid size)

Optimization tips:
- Enable `use_numba: true` for 5-10× speedup
- Reduce `nx` and `nt` for lower latency
- Increase resources for larger grids

## Security

- **Non-root container**: UID 1000, fsGroup 2000
- **Read-only rootfs**: No file writes except temp dirs
- **Dropped capabilities**: ALL capabilities dropped
- **Rate limiting**: 20 req/s per IP
- **Audit logging**: SHA256 request hashing
- **PII masking**: Sensitive data hashed in logs

See `docs/qlw/SECURITY.md` for full security policy.

## Integration with TACL

QLW outputs are designed for TACL integration:

```python
# TACL gate decision
hard_gate_active = result.meta["hard_gate_trigger"]
soft_penalty = result.meta["soft_weight_penalty"]

if hard_gate_active.any():
    # Block action or require approval
    action = "BLOCKED"
else:
    # Apply soft penalty to action weights
    action_weight *= soft_penalty
```

## Troubleshooting

### High Latency
- Reduce `nx` or `nt` in config
- Check CPU/memory limits
- Enable Numba JIT compilation

### Unstable Results
- Increase `nt` for longer time series
- Adjust `gamma_lo` / `gamma_hi` bounds
- Check CFL condition: `c·dt/dx < 1`

### High Forbidden Ratio
- Switch to `forbidden_mode: pid` for adaptation
- Adjust `pid_target` in config
- Review market volatility

## References

1. Newmark, N. M. (1959). "A method of computation for structural dynamics"
2. Berenger, J.-P. (1994). "A perfectly matched layer for the absorption of electromagnetic waves"
3. Kantelhardt, J. W., et al. (2002). "Multifractal detrended fluctuation analysis"
4. Åström, K. J., & Hägglund, T. (1995). "PID Controllers: Theory, Design, and Tuning"

## License

MIT License - see LICENSE file

## Contributing

See main repository CONTRIBUTING.md

## Support

For questions or issues:
- GitHub Issues: [repository]/issues
- Documentation: `docs/qlw/`
- Security: See `docs/qlw/SECURITY.md`
