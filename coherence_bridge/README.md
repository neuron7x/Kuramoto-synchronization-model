# CoherenceBridge v0.1

> GeoSync physics signals → OTS Capital execution engine

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)]()
[![proto3](https://img.shields.io/badge/proto3-12_fields-244c5a?style=for-the-badge)]()
[![gRPC](https://img.shields.io/badge/gRPC-StreamSignals-244c5a?style=for-the-badge&logo=google&logoColor=white)]()
[![Kafka](https://img.shields.io/badge/Kafka-coherence.signals.v1-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)]()
[![QuestDB](https://img.shields.io/badge/QuestDB-400k_rows/sec-E8457C?style=for-the-badge)]()
[![Grafana](https://img.shields.io/badge/Grafana-6_panels_5s-F46800?style=for-the-badge&logo=grafana&logoColor=white)]()
[![Docker](https://img.shields.io/badge/Docker-multi--stage-2496ED?style=for-the-badge&logo=docker&logoColor=white)]()
[![Tests](https://img.shields.io/badge/Tests-173_green-success?style=for-the-badge)]()
[![ruff](https://img.shields.io/badge/ruff-0_violations-success?style=for-the-badge)]()
[![mypy](https://img.shields.io/badge/mypy-strict-success?style=for-the-badge)]()
[![Physics](https://img.shields.io/badge/Invariants-T1--T13_verified-9B59B6?style=for-the-badge)]()
[![Active Inference](https://img.shields.io/badge/Active_Inference-45%%_TRADE-blueviolet?style=for-the-badge)]()
[![PR Gate](https://github.com/neuron7xLab/GeoSync/actions/workflows/pr-gate.yml/badge.svg)](https://github.com/neuron7xLab/GeoSync/actions/workflows/pr-gate.yml)
[![Physics Invariants](https://github.com/neuron7xLab/GeoSync/actions/workflows/physics-invariants.yml/badge.svg)](https://github.com/neuron7xLab/GeoSync/actions/workflows/physics-invariants.yml)

## Architecture

```
GeoSync physics kernel
  γ (PSD-derived) · R (Kuramoto) · κ (Augmented Forman-Ricci) · λ (Lyapunov)
              ↓
     CoherenceBridge v0.1
              ↓
┌─────────────────────────────────────────┐
│  GeoSyncDecisionEngine                  │
│  ├── UncertaintyEstimator               │
│  │     risk σ₁ = 1 - confidence         │
│  │     ambiguity σ₂ = |dγ/dt|/γ        │
│  ├── RegimeMemory (Dirichlet 5×5)       │
│  │     surprise = -log₂ P(new|prev)     │
│  └── EpistemicActionModule              │
│        TRADE 45% / OBSERVE 40% / ABORT  │
├─────────────────────────────────────────┤
│  Transport layer                        │
│  gRPC StreamSignals + GetSnapshot       │
│  Kafka → coherence.signals.v1           │
│  QuestDB ILP batch → ASOF JOIN ready    │
│  HTTP/SSE + Prometheus /metrics         │
└─────────────────────────────────────────┘
              ↓
OTS Capital: EKF sees OFI · Ricci sees topology
RF meta-labeler: 7 orthogonal physics features
```

## Signal Contract (12 fields, immutable, T1-T13 verified)

| Field | Type | Constraint | Description |
|---|---|---|---|
| `gamma` | float64 | (0, 3) | γ=2H+1, DERIVED from PSD. Never assigned. |
| `order_parameter_R` | float64 | [0, 1] | Kuramoto synchrony |
| `ricci_curvature` | float64 | R | Augmented Forman-Ricci |
| `lyapunov_max` | float64 | R | Max Lyapunov exponent |
| `regime` | Regime | enum | COHERENT / METASTABLE / DECOHERENT / CRITICAL |
| `regime_confidence` | float64 | [0, 1] | Posterior probability |
| `regime_duration_s` | float64 | >= 0 | Seconds since last transition |
| `signal_strength` | float64 | [-1, 1] | Phase distribution asymmetry |
| `risk_scalar` | float64 | [0, 1] | max(0, 1 - |γ - 1|) |
| `sequence_number` | uint64 | monotonic | Per instrument |
| `timestamp_ns` | int64 | UTC ns | Nanosecond timestamp |
| `instrument` | str | non-empty | e.g. "EURUSD" |

## Physics Invariants

```python
# INV-1: γ DERIVED, never assigned
gamma = estimator.compute(data)  # only valid form

# INV-2: formula (numerically verified)
assert abs(gamma - (2 * hurst + 1)) < 1e-10

# INV-3: risk gate
risk_scalar = max(0.0, 1.0 - abs(gamma - 1.0))

# INV-4: membrane — geosync/ never imports coherence_bridge/

# INV-5: RiskGate fail-closed — adjusted_size <= requested_size
```

## Quick Start

```bash
docker compose up -d
python main.py
# gRPC:    localhost:50051
# HTTP:    localhost:8080
# Grafana: localhost:3000
# QuestDB: localhost:9000
```

## For Ali Askar / OTS Capital

```go
// Go client — Kafka consumer
conn, _ := grpc.Dial("localhost:50051", grpc.WithInsecure())
client := pb.NewCoherenceBridgeClient(conn)
stream, _ := client.StreamSignals(ctx, &pb.StreamRequest{})
for {
    signal, _ := stream.Recv()
    // signal.Gamma, signal.Regime, signal.RiskScalar
    // → RF meta-labeler feature input
}
```

## References

- Peng et al. (1994) — DFA
- Peters (2019) — Ergodicity Economics
- Forman (2003) — Discrete Morse Theory / Ricci curvature
- Rosenstein et al. (1993) — Lyapunov exponents

---
*neuron7xLab × OTS Capital — 2026*
