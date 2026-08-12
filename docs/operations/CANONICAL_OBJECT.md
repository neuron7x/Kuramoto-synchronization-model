# CANONICAL_OBJECT.md — GeoSync System Definition

## What GeoSync IS

GeoSync is a **quantitative trading infrastructure platform** with a
**neuroscience-inspired risk management layer**. It combines classical
quantitative finance (Kelly criterion, Sharpe optimization, circuit breakers)
with computational neuroscience models (serotonin aversive signaling,
dopamine reward prediction, GABAergic inhibition, Kuramoto synchronization)
into a unified, mathematically validated decision pipeline.

It is a **research-grade production framework** — engineered to institutional
standards but not yet battle-tested with real capital at scale.

## What It Computes

```
Market Data (OHLCV)
    │
    ▼
┌─────────────────────────────────┐
│  Kuramoto Phase Synchronization │ → Order Parameter R ∈ [0,1]
│  (Hilbert transform, N bands)   │   (market regime coherence)
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  HPC Active Inference v4        │ → PWPE (prediction error)
│  (Precision-Weighted PE,        │ → Action selection
│   Self-Rewarding DRL)           │ → State entropy
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│            NeuroSignalBus (coordination layer)       │
│                                                      │
│  Dopamine RPE ←── execution P&L (Schultz 1997 TD)   │
│  Serotonin    ←── stress/drawdown (ODE, RK4, Lyap.) │
│  GABA inhib.  ←── VIX + volatility (sigmoid gate)   │
│  NAk energy   ←── arousal state                      │
│  Kuramoto R   ←── phase synchrony                    │
│  ECS free E.  ←── homeostatic regulator (Lyapunov)   │
│  HPC PWPE     ←── prediction surprise                │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│  Integrated Trading Decision                     │
│                                                  │
│  should_hold = serotonin > threshold ∨ crisis    │
│  position    = kelly_base                        │
│               × coherence_scale(R)               │
│               × (1 - gaba_inhibition)            │
│               × regime_dampening                 │
│  learning_rate = base_lr × |RPE| × NAk × 1/PWPE │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Execution Engine               │
│  OMS → Circuit Breaker → Order  │
│  Kraken / Binance / Coinbase    │
└─────────────────────────────────┘
```

## Mathematical Foundations (with citations)

| Component | Model | Citation | Validated |
|-----------|-------|----------|-----------|
| Dopamine RPE | Temporal Difference Learning | Schultz 1997 *Science* | ✅ Unit tests |
| Serotonin ODE | 5-HT patience hypothesis | Miyazaki et al. 2014 *Current Biology* | ✅ RK4 + Lyapunov proof |
| GABA gate | GABAergic motor inhibition | Mink 1996 *Progress in Neurobiology* | ✅ Sigmoid + STDP |
| Kuramoto sync | Phase oscillator model | Kuramoto 1975; Breakspear 2010 | ✅ Hilbert transform |
| Kelly fraction | Optimal bet sizing | Kelly 1956 *Bell System Tech J.* | ✅ Bounded [0,1] |
| Free Energy | Free Energy Principle | Friston 2009 *Nature Reviews Neuroscience* | ✅ Lyapunov monotonicity |
| Active Inference | HPC + PWPE | Friston 2009; Mathys 2011 | ✅ PWPE non-negative |
| Ricci flow | Ollivier-Ricci curvature | Ollivier 2009 *J. Funct. Anal.* | ⚠️ Needs analytic validation |
| NA/ACh arousal | Locus coeruleus model | Aston-Jones & Cohen 2005 | ⚠️ Minimal integration |

## Allowed Claims

- GeoSync implements a neuroscience-inspired risk management architecture
- All ODE subsystems have Lyapunov stability proofs
- The Signal Bus provides deterministic, thread-safe neuromodulator coordination
- 8000+ automated tests validate functional correctness
- The system is designed for institutional-grade deployment

## Forbidden Claims

- ❌ "GeoSync generates alpha" — not validated with real market data
- ❌ "Production-proven" — has not traded real capital
- ❌ "Better than X" — no head-to-head comparison exists
- ❌ "Mathematically optimal" — heuristic, not proven optimal
- ❌ "Neuroscience-accurate" — inspired by, not faithful simulation of

## Technology Readiness Level

**TRL 6 — System prototype demonstration in relevant environment**

| Criterion | Status |
|-----------|--------|
| Core algorithms implemented | ✅ |
| Unit + integration tests | ✅ 8100+ |
| CI/CD pipeline | ✅ GitHub Actions |
| API server with auth | ✅ FastAPI + mTLS |
| Exchange adapters | ✅ Kraken, Binance, Coinbase |
| Paper trading | ⚠️ Shadow module exists, needs integration |
| Live trading | ❌ Not attempted |
| Backtesting on real data | ❌ Synthetic only |
| Performance benchmarks | ⚠️ Claimed, not measured |
| Peer review | ❌ |

## Validation Status Per Module

| Module | Tests | Coverage | Math Proof | Live Tested |
|--------|-------|----------|------------|-------------|
| NeuroSignalBus | 33 | 100% | N/A (data) | ❌ |
| SerotoninODE | 15 | 95%+ | ✅ Lyapunov | ❌ |
| DopamineAdapter | 15 | 95%+ | ✅ TD error | ❌ |
| GABAPositionGate | 11 | 95%+ | ✅ Sigmoid | ❌ |
| KuramotoKelly | 13 | 90%+ | ✅ Hilbert | ❌ |
| ECSLyapunov | 9 | 90%+ | ✅ Lyapunov | ❌ |
| HPCNeuroBridge | 14 | 90%+ | ✅ PWPE | ❌ |
| API Server | 101 | 85%+ | N/A | ❌ |
| Execution Engine | ~200 | 72% | N/A | ❌ |
| Kuramoto Core | ~50 | 80%+ | ✅ Phase | ❌ |

## What Comes Next

1. **Historical backtesting** on real BTC/ETH OHLCV data (2020-2025)
2. **Paper trading** via shadow execution module
3. **Performance benchmarking** — replace all claims with measurements
4. **Parameter sensitivity analysis** — which params matter, which don't
5. **Peer review** by independent quant researcher
