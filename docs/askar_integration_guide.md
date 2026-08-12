# CoherenceBridge → OTS Integration Guide

## 1. QUICKSTART (5 min)

```bash
cd coherence-bridge
docker compose up -d

# Health check
grpcurl -plaintext localhost:50051 coherence_bridge.v1.CoherenceBridge/Health

# Live signal (HTTP)
curl localhost:8080/signal/EURUSD

# Stream (SSE)
curl -N "localhost:8080/stream?instruments=EURUSD,GBPUSD&interval_ms=1000"

# Prometheus metrics
curl localhost:8080/metrics

# Grafana dashboard
open http://localhost:3000  # QuestDB datasource pre-configured
```

## 2. OTP INTEGRATION (Go)

### Generate Go stubs from proto

```bash
protoc -I coherence_bridge/proto \
  --go_out=. --go-grpc_out=. \
  coherence_bridge/proto/coherence_bridge.proto
```

### gRPC client

```go
import cbv1 "github.com/neuron7xLab/coherence-bridge/proto/v1"

conn, _ := grpc.Dial("localhost:50051", grpc.WithInsecure())
client := cbv1.NewCoherenceBridgeClient(conn)
stream, _ := client.StreamSignals(ctx, &cbv1.SignalRequest{
    Instruments:   []string{"EURUSD", "GBPUSD"},
    MinIntervalMs: 1000,
})
for {
    sig, _ := stream.Recv()
    fmt.Printf("γ=%.4f R=%.4f regime=%s risk=%.4f\n",
        sig.Gamma, sig.OrderParameterR, sig.Regime, sig.RiskScalar)
}
```

### Kafka consumer for OTP strategy framework

See `examples/go-client/otp_strategy_consumer.go`:

```go
consumer := NewRegimeConsumer("kafka:9092", "coherence.signals.v1")
go consumer.Run(ctx)

// In your strategy loop:
if consumer.ShouldBlockNewPositions("EURUSD") {
    continue // CRITICAL or DECOHERENT → no new orders
}
size := consumer.RiskScaledSize("EURUSD", basePosition)
orderRouter.Submit("EURUSD", side, size)
```

Key methods:
- `ShouldBlockNewPositions(inst)` → blocks on CRITICAL, DECOHERENT, UNKNOWN, or risk<0.3
- `IsMetastableEdge(inst)` → true when METASTABLE + risk>0.7 + confidence>0.6
- `RiskScaledSize(inst, base)` → base × risk_scalar (0 if blocked)
- `GetGapCount(inst)` → sequence gap counter for data quality monitoring

## 3. BACKTEST SETUP

### Generate historical signals

```bash
python -m coherence_bridge.backfill \
  --instruments EURUSD GBPUSD USDJPY \
  --start 2025-01-01 --end 2025-12-31 \
  --output backfill_2025.parquet \
  --questdb-host localhost
```

### ASOF JOIN with orderbook snapshots

```sql
SELECT
    ob.timestamp, ob.instrument,
    ob.bid_price, ob.ask_price,
    (ob.bid_volume - ob.ask_volume) / (ob.bid_volume + ob.ask_volume) AS obi,
    cs.gamma, cs.ricci_curvature, cs.regime,
    cs.risk_scalar, cs.signal_strength
FROM orderbook_snapshots ob
ASOF JOIN coherence_signals cs ON (ob.instrument = cs.instrument)
WHERE ob.timestamp BETWEEN '2025-01-01' AND '2025-12-31'
    AND ob.instrument = 'EURUSD'
ORDER BY ob.timestamp
```

### Regime P&L attribution

```sql
SELECT cs.regime, count(*), avg(t.pnl), stddev(t.pnl)
FROM trades t
ASOF JOIN coherence_signals cs ON (t.instrument = cs.instrument)
GROUP BY cs.regime
ORDER BY avg(t.pnl) DESC
```

Full query library: `coherence_bridge/questdb_queries.py` (6 pre-built queries).

## 4. RF META-LABELING INTEGRATION

```python
from coherence_bridge.feature_exporter import RegimeFeatureExporter

exporter = RegimeFeatureExporter()

# Single signal → 7 features
features = exporter.to_ml_features(signal)
# → {'gamma_distance': 0.2, 'r_coherence': 0.6, 'ricci_sign': -1.0,
#     'lyapunov_sign': 1.0, 'regime_encoded': 1.0,
#     'regime_confidence': 0.85, 'risk_scalar': 0.8}

# Batch → DataFrame for training
df = exporter.to_questdb_feature_table(signals)
# Columns: timestamp, instrument, gamma_distance, r_coherence,
#          ricci_sign, lyapunov_sign, regime_encoded,
#          regime_confidence, risk_scalar

# Add to existing RF pipeline:
X_train = pd.concat([your_ofi_features, df[ML_COLUMNS]], axis=1)
```

Feature descriptions:
| Feature | Range | Meaning |
|---------|-------|---------|
| gamma_distance | [0, ∞) | Distance from metastable (1/f noise). 0 = edge of chaos |
| r_coherence | [0, 1] | Kuramoto sync. 0=random, 1=herding |
| ricci_sign | {-1, 0, 1} | Network topology. -1=fragile bottleneck |
| lyapunov_sign | {-1, 0, 1} | Stability. +1=chaotic sensitivity |
| regime_encoded | {0,1,2,3,-1} | COHERENT=0, METASTABLE=1, DECOHERENT=2, CRITICAL=3 |
| regime_confidence | [0, 1] | Posterior probability of regime |
| risk_scalar | [0, 1] | Position size multiplier |

## 5. RISK GATE WIRING

```python
from coherence_bridge.risk_gate import CoherenceRiskGate

gate = CoherenceRiskGate(engine, fail_closed=True)

# Before every order submission:
decision = gate.apply("EURUSD", intended_size=1.0)
if decision.allowed:
    submit_order("EURUSD", decision.adjusted_size)
else:
    log(f"Blocked: {decision.reason}")
```

Gate logic:
| Regime | risk_scalar | Action |
|--------|-------------|--------|
| METASTABLE | > 0.7 | Pass, size × risk_scalar |
| COHERENT | > 0.5 | Pass, size × risk_scalar × 0.6 |
| DECOHERENT | any | Block |
| CRITICAL | any | Block + alert |
| unavailable | any | Block (fail-closed) |

Invariants:
- `adjusted_size <= intended_size` always (gate never amplifies)
- No signal = no trade (fail-closed default)
- `risk_scalar` derived from γ distance to 1.0 (never assigned)
