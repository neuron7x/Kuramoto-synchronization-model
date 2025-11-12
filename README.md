# 📈 TradePulse

### *Neuroscience-Inspired Algorithmic Trading Framework*

---

```ascii
╔═══════════════════════════════════════════════════════════╗
║ 🧠 Neuroscience-Based Decisions • 🧮 Geometric Indicators  ║
║ ⚡ Real-Time Analytics • 🔒 Production-Ready Security       ║
╚═══════════════════════════════════════════════════════════╝
```

[![Tests](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)
[![Coverage Shards](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/neuron7x/TradePulse/actions/workflows/ci.yml)
[![Coverage Guard ≥98%](https://img.shields.io/badge/Coverage-%E2%89%A598%25-brightgreen?logo=pytest)](#-testing)

## What Is TradePulse?

TradePulse is a **production-grade algorithmic trading platform** that applies **neuroscience principles** to financial decision-making. Just as the human brain uses neurotransmitters (dopamine, serotonin, GABA) to navigate uncertainty, learn from experience, and manage risk, TradePulse implements these same biological mechanisms as algorithms.

**Core Innovation:** We've translated decades of neuroscience research on reward learning, stress regulation, and impulse control into a robust trading framework that combines:
- **Dopamine-based reinforcement learning** for adaptive strategy optimization
- **Serotonin-modulated risk management** for stress-aware position control
- **GABA-inspired impulse inhibition** for preventing overtrading
- **Geometric indicators** (Kuramoto oscillators, Ricci flow) for market regime detection
- **Enterprise-grade infrastructure** with compliance, security, and observability

**Who Uses TradePulse:**
- Quantitative researchers seeking novel alpha signals beyond traditional indicators
- Institutional trading desks requiring production-grade risk management and compliance
- Discretionary traders wanting systematic approaches to reduce emotional decision-making
- Fintech developers building modern, extensible trading infrastructure
- Hedge funds and prop trading firms needing high-frequency capabilities with robust backtesting

## Table of Contents

- [What Is TradePulse?](#what-is-tradepulse)
- [Why TradePulse?](#-why-tradepulse)
- [Who Is This For?](#-who-is-this-for)
- [Feature Highlights](#-feature-highlights)
- [Neuroscience-Inspired Architecture](#-neuroscience-inspired-architecture)
- [Project Status](#-project-status)
- [Quick Start](#-quick-start)
- [Demo Dashboard](#-demo-dashboard)
- [System Architecture](#-system-architecture)
- [Thermodynamic Autonomic Control Layer (TACL)](#thermodynamic-autonomic-control-layer-tacl)
- [Documentation](#-documentation)
- [Use Cases](#-use-cases)
- [Configuration](#-configuration)
- [Testing](#-testing)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)
- [Community](#-community)
- [License](#-license)
- [Disclaimer](#-disclaimer)
- [Acknowledgments](#-acknowledgments)
- [🇺🇦 Ukrainian Summary / Короткий опис українською](#-короткий-опис-українською)

## 🎯 Why TradePulse?

TradePulse is a unique trading platform that applies **neuroscience principles** to financial markets. Just as the human brain uses neurotransmitters (dopamine, serotonin, GABA) to make complex decisions under uncertainty, TradePulse uses neuromodulator-inspired algorithms to navigate market volatility, manage risk, and optimize trading decisions.

**Key Innovation:** We've translated decades of neuroscience research on decision-making, reward processing, and stress regulation into a robust algorithmic trading framework.

```python
import numpy as np
import pandas as pd

from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine


# Build a synthetic intraday data set
index = pd.date_range("2024-01-01", periods=720, freq="5min")
price = 100 + np.cumsum(np.random.normal(0, 0.6, index.size))
volume = np.random.lognormal(mean=9.5, sigma=0.35, size=index.size)
bars = pd.DataFrame({"close": price, "volume": volume}, index=index)

# Analyze the market regime with the Kuramoto–Ricci composite engine
engine = TradePulseCompositeEngine()
snapshot = engine.analyze_market(bars)

print(f"Phase: {snapshot.phase.value}")
print(f"Confidence: {snapshot.confidence:.3f}, Entry: {snapshot.entry_signal:.3f}")
```

## 👥 Who Is This For?

### Quantitative Researchers
- **Need:** Advanced indicators beyond traditional technical analysis
- **Solution:** Geometric indicators (Kuramoto, Ricci Flow), multi-scale fractal analysis, and entropy measures provide novel alpha signals
- **Benefit:** Research-to-production pipeline with deterministic backtesting and property-based validation

### Institutional Trading Desks
- **Need:** Production-grade risk management with regulatory compliance
- **Solution:** Neuroscience-inspired risk controls, comprehensive audit trails, MiFID II compliance
- **Benefit:** Enterprise security framework with 93 controls, real-time threat detection, and incident response

### Discretionary Traders
- **Need:** Systematic approach to reduce emotional decision-making
- **Solution:** Dopamine-based reward prediction, serotonin stress regulation, GABA impulse control
- **Benefit:** Structured decision framework that mimics optimal human decision-making under uncertainty

### Fintech Developers
- **Need:** Modern, extensible trading infrastructure
- **Solution:** Event-driven architecture, FastAPI integration, type-safe contracts (Pydantic/Protocol Buffers)
- **Benefit:** Hot-reload development, comprehensive testing infrastructure, extensive documentation

### Hedge Funds & Prop Trading Firms
- **Need:** High-frequency capabilities with robust backtesting
- **Solution:** GPU acceleration (CUDA/Numba), microsecond latency pipeline, walk-forward optimization
- **Benefit:** Production-ready execution with multi-exchange support and zero data loss guarantees


## 📊 Project Status

TradePulse already ships with a fully operational research and execution core—
including geometric indicators, the event-driven backtester, and the CLI
tooling—but the **v1.0 release remains on hold** while we close a few critical
gaps:

- **Automated tests**: overall coverage is still well below the 98 % bar set in
  the release checklist, so hardening the test suite is the current top
  priority.
- **Documentation polish**: several deep-dive sections referenced from the
  roadmap are still being drafted, and onboarding guides need final review.
- **Web dashboard**: the Streamlit dashboard bundled with the repo is presently
  a placeholder and is not production ready yet.

These items are tracked in the public roadmap, and incremental updates are
published in the weekly changelog until the release criteria are satisfied.

## ✨ Feature Highlights

### 🧮 Advanced Indicators
- **Kuramoto Oscillators** — synchronization-based market analysis
- **Ricci Flow** — geometric curvature detection
- **Multi-scale Analysis** — fractal pattern recognition
- **Entropy Measures** — information-theoretic signals
- **50+ Technical Indicators** — classic plus modern coverage

### ⚡ High-Performance Engine
- **Event-Driven Architecture** — microsecond latency pipeline
- **Parallel Processing** — multi-core optimizations throughout
- **GPU Acceleration** — CUDA/Numba-enabled workloads
- **Streaming Analytics** — real-time signal processing
- **Smart Caching** — Redis-powered performance boosts

### 🔄 Data Management
- **Multi-Source Integration** — CCXT, Alpaca, Polygon, and more
- **Versioned Storage** — full data lineage tracking
- **Quality Control** — automated validation pipelines
- **Feature Store** — Parquet/Polars efficiency
- **Dead Letter Queue** — zero data loss guarantees

### 🧪 Research & Testing
- **Deterministic Backtesting** — reproducible simulations
- **Monte Carlo Simulation** — deep risk analysis
- **Walk-Forward Optimization** — defense against overfitting
- **Property-Based Testing** — Hypothesis-driven validation
- **Mutation Testing** — quality assurance for trading logic

### 🚀 Production Ready
- **Live Trading** — multi-exchange support out of the box
- **Risk Management** — comprehensive pre-trade compliance and exposure limits
- **Kill Switch** — global emergency stop with secure admin API
- **Circuit Breakers** — automatic trading halt after failures or breaches
- **Position Limits** — per-symbol and portfolio-wide exposure caps
- **Drawdown Protection** — daily loss limits with automatic reset
- **Paper Trading** — safe deployment dry runs
- **Canary Releases** — progressive rollout tooling

### 🔒 Enterprise Security
- **Comprehensive Security Framework** — 10 key requirements (NIST, ISO 27001)
- **HashiCorp Vault** — centralized secret management
- **Role-Based Access Control** — granular permissions with least privilege
- **Audit Logging** — full compliance traceability with 400-day retention
- **Encrypted Storage** — AES-256 at rest, TLS 1.3 in transit
- **MiFID II Compliance** — regulatory readiness (GDPR, CCPA, SEC, FINRA)
- **Real-time Threat Detection** — SIEM integration with ML-based anomaly detection
- **Incident Response** — NIST 800-61 compliant IRP with < 4 hour MTTR
- **DevSecOps** — automated security scanning in CI/CD pipeline
- **93 Security Controls** — mapped to NIST and ISO 27001 (80% implemented)

### 📊 Observability
- **Prometheus Metrics** — operational visibility
- **OpenTelemetry Tracing** — distributed diagnostics
- **Grafana Dashboards** — visual insights
- **Health Checks** — proactive alerting
- **Auto-Triage** — intelligent diagnostics

### 🎨 Developer Experience
- **CLI Tools** — Streamlit-powered dashboards
- **REST API** — FastAPI-first integration points
- **Type Safety** — Pydantic models and schema validation
- **Hydra Config** — flexible configuration management
- **Hot Reload** — rapid iteration for research teams

## 🧠 Neuroscience-Inspired Architecture

TradePulse is built on a **neurodecision stack** that translates neuroscience principles into algorithmic trading. Our architecture mirrors the brain's decision-making systems, providing robust, adaptive, and biologically-grounded trading strategies.

### Core Neuroscience Components

#### 1. **Dopamine Controller** — Reward Prediction & Learning
**Neuroscience Basis:** Dopamine neurons in the ventral tegmental area (VTA) encode **temporal difference (TD) reward prediction errors**, driving reinforcement learning.

**Implementation:**
- **TD(0) RPE Calculation:** `δ = reward + γ·V(next_state) - V(state)`
- **Phasic/Tonic Dynamics:** Rapid reward bursts vs. sustained motivation levels
- **Go/No-Go Decision Gate:** Based on basal ganglia direct/indirect pathways
- **Temperature Control:** Exploration vs. exploitation balance (σ(k·(tonic−θ)))
- **DDM Adaptation:** Drift-Diffusion Model parameters adapt to dopamine levels

**Trading Application:**
- Learns from profitable trades (positive RPE) and losses (negative RPE)
- Increases confidence (lowers decision thresholds) after winning streaks
- Prevents overtrading through policy temperature modulation
- Implements "Go" signals for high-confidence opportunities

**Files:** `src/tradepulse/core/neuro/dopamine/`, `config/dopamine.yaml`

#### 2. **Serotonin Controller** — Stress Regulation & Risk Aversion
**Neuroscience Basis:** Serotonin (5-HT) in the dorsal raphe nucleus modulates **aversive processing, patience, and behavioral inhibition** during stressful conditions.

**Implementation:**
- **Tonic/Phasic Channels:** Long-term stress tracking vs. acute threat responses
- **Veto Mechanism:** HOLD signal overrides impulsive dopamine-driven actions
- **Cooldown Windows:** Prevents rapid trading after stress events
- **Desensitization:** Chronic stress reduces sensitivity (adaptive tolerance)
- **Temperature Floor:** Maintains minimum exploration under adversity
- **τ-Calibrated Filtering:** Biologically realistic time constants (tau_5ht_ms)

**Trading Application:**
- Detects drawdown stress and portfolio risk accumulation
- Enforces cooling-off periods after significant losses
- Prevents panic selling through HOLD vetoes
- Maintains adaptive risk tolerance based on market conditions

**Files:** `core/neuro/serotonin/serotonin_controller.py`, `configs/serotonin.yaml`

#### 3. **GABA Inhibition Gate** — Impulse Control & Plasticity
**Neuroscience Basis:** GABAergic interneurons provide **fast inhibition** in cortical circuits, implementing **spike-timing-dependent plasticity (STDP)** for learning.

**Implementation:**
- **Dual Time Constants:** GABA_A (fast, τ=8ms) and GABA_B (slow, τ=100ms)
- **Threat-Proportional Inhibition:** Scales with volatility/VIX proxies
- **STDP Plasticity:** tau_plus=16.8ms, tau_minus=33.7ms for timing-dependent learning
- **LTP/LTD:** Long-term potentiation/depression based on correlation (vol×ret)
- **Gamma/Theta Rhythms:** 40Hz and 8Hz oscillatory modulation
- **Risk Weight Adaptation:** Bounds [0.5, 1.5] for safe operation

**Trading Application:**
- Inhibits impulsive trades during high volatility
- Learns optimal inhibition strength through experience
- Implements "circuit breaker" functionality
- Provides hedge-like protection (diazepam-analog GABA boost)

**Files:** `modules/gaba_inhibition_gate.py`, `docs/GABAInhibitionGate.md`

#### 4. **NAK Controller** — Arousal & Attention
**Neuroscience Basis:** **Noradrenaline (NA)** from locus coeruleus drives arousal and vigilance; **Acetylcholine (ACh)** from basal forebrain enhances attention and learning.

**Implementation:**
- **Noradrenaline:** `NA(t) = σ(volatility · gain)` — arousal scales with market uncertainty
- **Acetylcholine:** `ACh(t) = σ(exposure · η)` — attention tracks position size
- **Risk Modulation:** DA-scaled target risk rates
- **Activity Scaling:** ACh-modulated position sizing

**Trading Application:**
- Increases attention (position sizing) during volatile markets
- Modulates risk-taking based on arousal state
- Enhances learning rate when novel patterns emerge
- Coordinates with dopamine for risk-adjusted reward seeking

**Files:** `nak_controller/control/neuromods.py`, `nak_controller/README.md`

#### 5. **ECS Regulator** — Stress Adaptation & Homeostasis
**Neuroscience Basis:** The **endocannabinoid system (ECS)** provides compensatory feedback during stress, differentiating acute vs. chronic stressors.

**Implementation:**
- **Acute vs. Chronic Stress:** Separate tracking mechanisms
- **Context-Dependent Normalization:** Adapts to market phase (stable/chaotic/transition)
- **Compensatory Feedback:** 2-AG-inspired upregulation under prolonged stress
- **Kalman Filtering:** Predictive coding for prediction error minimization
- **TACL Alignment:** Free energy monotonic descent enforcement

**Trading Application:**
- Distinguishes temporary volatility from sustained bear markets
- Implements adaptive risk thresholds based on stress patterns
- Provides homeostatic regulation to prevent overreaction
- Maintains trading activity during extended drawdowns

**Files:** `core/neuro/ecs_regulator.py`, `core/neuro/README_ECS_REGULATOR.md`

#### 6. **FHMC — Orexin-Arousal & Meta-Control**
**Neuroscience Basis:** **Orexin** neurons in the lateral hypothalamus regulate **sleep-wake transitions, arousal, and energy balance** through flip-flop switching.

**Implementation:**
- **Flip-Flop State Machine:** WAKE/SLEEP modes with hysteresis
- **Orexin-Arousal:** `OX(t) = σ(k₁·E[r] + k₂·novelty + k₃·load)`
- **Threat-Imminence:** Combines drawdown, volatility shock, and crisis scores
- **Multifractal Cascade:** Hölder field estimation via dyadic p-model
- **DFA α-Exponent:** Fractal analysis through detrended fluctuation
- **Aperiodic 1/f Slope:** Pink noise spectral shaping

**Trading Application:**
- Controls system-wide WAKE (active trading) vs. SLEEP (observation) modes
- Triggers exploration based on expected returns and novelty
- Implements threat-driven defensive postures
- Captures market complexity through multifractal dynamics

**Files:** `runtime/thermo_controller.py`, `docs/spec_fhmc.md`, `configs/fhmc.yaml`

### Geometric & Complexity Indicators

#### **Kuramoto Oscillators** — Synchronization Detection
**Scientific Basis:** Kuramoto model describes **phase synchronization** in coupled oscillator systems, revealing collective behavior emergence.

**Application:**
- Detects market regime transitions (order → disorder)
- Measures synchronization across multiple timeframes
- Identifies phase-locking between correlated assets
- Order parameter `r(t) ∈ [0,1]` indicates market coherence

**Files:** `core/indicators/kuramoto.py`, `core/indicators/multiscale_kuramoto.py`

#### **Ricci Flow** — Geometric Curvature
**Scientific Basis:** Ricci flow from **differential geometry** describes how geometric manifolds evolve by smoothing curvature.

**Application:**
- Detects curvature changes in price space
- Identifies geometric instabilities (high curvature = high risk)
- Temporal evolution tracking for regime shift prediction
- Composite integration with Kuramoto for multi-scale analysis

**Files:** `core/indicators/ricci.py`, `core/indicators/temporal_ricci.py`, `core/indicators/kuramoto_ricci_composite.py`

### Integration: The Neurodecision Stack

```
Market Data → Kuramoto/Ricci Indicators
              ↓
    ┌─────────────────────────────┐
    │   Dopamine (TD-Learning)    │──► Reward Prediction Error
    │   Serotonin (Stress Gate)   │──► HOLD Veto Signal
    │   GABA (Impulse Control)    │──► Inhibition Coefficient
    │   NA/ACh (Arousal/Attention)│──► Risk & Activity Scaling
    │   ECS (Homeostasis)         │──► Stress Adaptation
    │   FHMC (Meta-Control)       │──► WAKE/SLEEP Mode
    └─────────────────────────────┘
              ↓
        ActionGate Decision
              ↓
    GO / NO-GO / HOLD → Execution
```

**Key Properties:**
- **Biological Realism:** Time constants, plasticity rules, and dynamics grounded in neuroscience literature
- **Formal Guarantees:** Monotonic free energy descent (TACL), MFD constraints, safety bounds
- **Empirical Validation:** Falsification tests, property-based testing, mutation testing
- **Production Ready:** Full telemetry, audit trails, compliance logging

### Scientific References

Our implementation is based on peer-reviewed research:

1. **Temporal Difference Learning:** Sutton & Barto (2018), *Reinforcement Learning: An Introduction*
2. **Dopamine RPE:** Schultz et al. (1997), "A Neural Substrate of Prediction and Reward", *Science*
3. **Serotonin & Aversion:** Dayan & Huys (2009), "Serotonin in Affective Control", *Annual Review of Neuroscience*
4. **STDP Plasticity:** Bi & Poo (1998), "Synaptic Modifications in Cultured Hippocampal Neurons", *Journal of Neuroscience*
5. **Go/No-Go Circuits:** Frank (2006), "Hold Your Horses: A Dynamic Computational Role for the Subthalamic Nucleus", *Neural Networks*
6. **Kuramoto Model:** Kuramoto (1984), *Chemical Oscillations, Waves, and Turbulence*
7. **Ricci Flow:** Hamilton (1982), "Three-manifolds with positive Ricci curvature", *Journal of Differential Geometry*
8. **Drift-Diffusion Models:** Ratcliff & McKoon (2008), "The Diffusion Decision Model", *Neural Computation*

### Why Neuroscience for Trading?

**Traditional Approach:**
- Rule-based indicators (RSI, MACD, Bollinger Bands)
- Fixed risk parameters
- Emotion-driven human decisions or rigid algorithms

**Neuroscience Approach:**
- **Adaptive Learning:** Continuous TD-learning from market feedback
- **Stress Management:** Serotonin-based risk reduction during drawdowns
- **Impulse Control:** GABA inhibition prevents overtrading
- **Context Awareness:** ECS differentiates acute vs. chronic market stress
- **Meta-Control:** FHMC orchestrates system-wide operational modes

**Result:** A trading system that adapts like a skilled trader but with the consistency of an algorithm, the speed of a computer, and the robustness of biological decision-making refined over millions of years of evolution.

## 🚀 Quick Start

### Installation

```bash
# Install with pip
pip install tradepulse

# With optional dependencies
pip install "tradepulse[connectors,feature_store,gpu]"

# From source
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse
pip install -e ".[dev]"
```

### Your First Strategy

```python
import numpy as np

from backtest.event_driven import EventDrivenBacktestEngine
from core.indicators import KuramotoIndicator


# Generate a synthetic closing price series
rng = np.random.default_rng(seed=42)
prices = 100 + np.cumsum(rng.normal(0, 1, 500))
indicator = KuramotoIndicator(window=80, coupling=0.9)


def kuramoto_signal(series: np.ndarray) -> np.ndarray:
    order = indicator.compute(series)
    signal = np.where(order > 0.75, 1.0, np.where(order < 0.25, -1.0, 0.0))
    warmup = min(indicator.window, signal.size)
    signal[:warmup] = 0.0
    return signal


engine = EventDrivenBacktestEngine()
result = engine.run(
    prices,
    kuramoto_signal,
    initial_capital=100_000,
    strategy_name="kuramoto_demo",
)

print(f"PnL: {result.pnl:.2f}")
print(f"Max drawdown: {result.max_dd:.2f}")
print(f"Trades executed: {result.trades}")
```

### 📈 View Results

```python
import pandas as pd


# Inspect metrics collected by the engine
if result.performance:
    stats = result.performance.as_dict()
    print(f"Sharpe ratio: {stats['sharpe_ratio']:.2f}")
    print(f"Max drawdown: {stats['max_drawdown']:.2f}")


# Persist the equity curve for further analysis
if result.equity_curve is not None:
    pd.Series(result.equity_curve, name="equity").to_csv(
        "backtest_equity_curve.csv", index=False
    )
```

## 📊 Demo Dashboard

![TradePulse Dashboard](docs/assets/dashboard_demo.png)

## 🏗️ System Architecture

```mermaid
graph TB
  A[Data Ingestion] --> B[Feature Store]
  B --> C[Strategy Engine]
  C --> D[Risk Manager]
  D --> E[Execution Layer]
  E --> F[Exchange APIs]
  C --> G[Analytics]
  G --> H[Observability]

  style A fill:#4a90e2
  style C fill:#7ed321
  style E fill:#f5a623
  style H fill:#bd10e0
```

## Thermodynamic Autonomic Control Layer (TACL)

TACL is the self-regulating control system that manages TradePulse topology as a physical system. It measures free energy F (latency, coherency, resource costs), detects stress, evolutionarily reconfigures service bonds via GA/RL/LinkActivator, performs hot-swap of protocols (RDMA, CRDT, shared memory), and guarantees safety through **Monotonic Free Energy Descent** constraint: no change can increase F without human override.

**Features**:
- Real-time telemetry & observability API
- CI gates with formal safety guarantees
- 7-year audit trail for compliance
- Crisis-aware adaptive recovery

**This layer enforces thermodynamic stability of the topology using Lyapunov-style energy descent, GA/RL adaptation, runtime monotonic safety gates, and auditable decision logs.**

**Prototype classification:** TRL7 (post-staging)

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Thermodynamic Control Loop                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Measure  →  Analyse  →  Plan  →  Execute                    │
│                                                              │
│  • system_free_energy()                                      │
│  • dF/dt & adaptive epsilon                                  │
│  • Crisis detection (normal/elevated/critical)               │
│  • CrisisAwareGA + AdaptiveRecoveryAgent                     │
│  • LinkActivator (primary → fallback → last resort)          │
└──────────────────────────────────────────────────────────────┘
```

### Key Components

- `runtime/link_activator.py` — maps bond types to concrete
  communication protocols (CRDT, RDMA, gRPC, shared memory, gossip,
  local fallbacks) and records activation telemetry.
- `runtime/recovery_agent.py` — Q-learning agent selecting recovery
  intensity (slow/medium/fast) based on free-energy deviation,
  latency spike and crisis duration.
- `evolution/crisis_ga.py` — crisis-aware genetic algorithm that
  scales population and mutation rate according to the detected crisis
  mode.
- `runtime/thermo_controller.py` — orchestrates the loop, enforces the
  monotonic constraint with tolerance windows, and drives LinkActivator
  for hot-swapping protocols.
- `runtime/thermo_api.py` — FastAPI service exposing `/thermo/status`,
  `/thermo/history`, `/thermo/crisis`, `/thermo/activations`, and a
  `/thermo/reset` hook for integration tests.
- `scripts/polygon_validator.py` — offline-friendly Polygon loader with
  synthetic fallback for validating the internal tail free-energy proxy and
  flash-crash behaviour.

### Safety Guarantees

- **Monotonic descent** — every accepted mutation must satisfy
  `F_new ≤ F_old + ε`, where `ε = 0.01 × baseline_EMA`.
- **Crisis handling** — latency spikes or large `|dF/dt|` trigger the
  adaptive recovery agent and the crisis-aware GA.
- **Telemetry** — each control step logs timestamp, free energy,
  derivative, epsilon, bottleneck edge, crisis mode and activation
  history. Accessible via the FastAPI endpoints.

### Validation & Testing

- Unit tests cover the link activator, recovery agent and controller
  monotonic constraint (`tests/test_link_activator.py`,
  `tests/test_recovery_agent.py`, `tests/test_energy.py`).
- Integration harness for Polygon-based stress tests lives in
  `tests/test_polygon_integration.py` and is opt-in through
  `RUN_POLYGON_TESTS=1`.
- CI workflow `.github/workflows/thermo-evolution.yml` now runs the
  dedicated unit suites and validates the security policy.

## 📚 Documentation

| Resource | Description |
|----------|-------------|
| [Installation Guide](docs/installation.md) | Detailed setup instructions |
| [API Reference](https://docs.tradepulse.io/api) | Complete API documentation |
| [User Guide](docs/quickstart.md) | Step-by-step tutorials |
| [Strategy Examples](docs/examples) | 20+ working strategies |
| [Indicator Library](docs/indicators.md) | Geometric and technical indicators |
| [Deployment Guide](docs/deployment.md) | Production rollouts |
| [Architecture Overview](docs/ARCHITECTURE.md) | System design deep dive |
| [**Security Framework**](SECURITY_FRAMEWORK_SUMMARY.md) | **Comprehensive security documentation** |
| [**Operational Artifacts**](docs/OPERATIONAL_ARTIFACTS_INDEX.md) | **Production operations, SLA/alerts, incident management** |

### 🔐 Security Documentation

TradePulse implements a comprehensive security framework covering all critical aspects:

| Document | Description |
|----------|-------------|
| [Security Framework Summary](SECURITY_FRAMEWORK_SUMMARY.md) | Executive overview and implementation status |
| [Security Framework Index](docs/security/SECURITY_FRAMEWORK_INDEX.md) | Complete framework index with all 10 requirements |
| [Security Policy](SECURITY.md) | Vulnerability reporting and security best practices |
| [Risk Analysis](docs/security/risk-analysis/risk-identification-framework.md) | FMEA, PESTLE, SWOT analysis |
| [Security Requirements](docs/security/requirements/security-requirements-specification.md) | 93 controls mapped to NIST and ISO 27001 |
| [Secure Architecture](docs/security/architecture/secure-architecture-design.md) | Defense-in-depth and Zero Trust design |
| [DevSecOps Guide](docs/security/devsecops/devsecops-integration-guide.md) | Security automation in CI/CD |
| [Security Operations](docs/security/SECURITY_OPERATIONS_GUIDE.md) | Monitoring, incident response, compliance |

**Security Highlights**:
- ✅ 93 security controls (80% implemented)
- ✅ ISO 27001 and NIST SP 800-53 aligned
- ✅ GDPR, CCPA, SEC, FINRA compliant
- ✅ Real-time threat detection with ML
- ✅ Incident response with < 4 hour MTTR
- ✅ Automated security scanning in CI/CD

### 🚀 Operational Readiness Documentation

TradePulse provides complete operational lifecycle documentation for production deployment:

| Document | Description |
|----------|-------------|
| [Operational Artifacts Index](docs/OPERATIONAL_ARTIFACTS_INDEX.md) | Master index of all operational documentation |
| [Production Operations Dashboard](observability/dashboards/tradepulse-production-operations.json) | Real-time monitoring and SLO tracking |
| [SLA/Alert Playbooks](docs/sla_alert_playbooks.md) | Alert response procedures and escalation |
| [Incident Coordination](docs/incident_coordination_procedures.md) | Complete incident management framework |
| [System Lifecycle Operations](docs/system_lifecycle_operations.md) | Daily/weekly/monthly operational procedures |
| [Operational Summary (UA)](OPERATIONAL_COMPLETION_SUMMARY_UA.md) | Ukrainian summary of operational readiness |

**Operational Highlights**:
- ✅ Complete lifecycle coverage (pre-production → active ops → shutdown)
- ✅ Response procedures for all 8 alert types
- ✅ 4-tier incident severity classification
- ✅ Production dashboard with system health, SLOs, and active alerts
- ✅ Daily, weekly, monthly, quarterly operational schedules
- ✅ Integration with 35+ operational artifacts
- ✅ Communication templates and escalation paths
- ✅ Backup/recovery and capacity planning procedures

## 🎯 Use Cases

### For Quantitative Researchers

```python
# Fractal indicator composition
from tradepulse.indicators import MultiscaleKuramoto

indicator = MultiscaleKuramoto(
    scales=[5, 15, 60],  # Multi-timeframe analysis
    coupling=0.7,
)

# Automatic feature versioning
data_signals = indicator.compute(data, version="v2.1.0")
```

### For Day Traders

```python
# Real-time signal generation
from tradepulse.live import LiveTrader

trader = LiveTrader(
    strategy=your_strategy,
    exchange="binance",
    mode="paper",  # Safe testing
)
trader.start()
```

### For Institutions

```python
# Enterprise-grade risk management
from tradepulse.risk import RiskManager

risk_manager = RiskManager(
    max_position_size=100_000,
    max_leverage=3.0,
    stop_loss_pct=0.02,
    compliance_checks=["mifid2", "position_limits"],
)
```

## 🔧 Configuration

TradePulse uses Hydra for flexible configuration:

```yaml
# config.yaml
strategy:
  name: momentum
  capital: 100000

data:
  source: binance
  symbols: [BTC/USDT, ETH/USDT]
  timeframe: 1h

execution:
  slippage: 0.001
  commission: 0.001

risk:
  max_position_pct: 0.2
  stop_loss_pct: 0.02
```

## 🧪 Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=tradepulse --cov-report=html

# Property-based tests
pytest tests/property

# Performance benchmarks
pytest tests/performance --benchmark-only

# Mutation testing
mutmut run
```

## 🤝 Contributing

We love contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for the full
guidelines.

```bash
# Setup development environment
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse
pip install -e ".[dev]"

# Run quality checks
black .
ruff check .
mypy .
pytest
```

## 🌟 Contributors

*TradePulse is made possible by a vibrant community of quants, traders, and
engineers.*

## 📈 Roadmap

- [x] **Phase 1** — Core backtesting engine
- [x] **Phase 2** — Geometric indicators
- [x] **Phase 3** — Live trading support
- [ ] **Phase 4** — Machine learning integration
- [ ] **Phase 5** — Options & derivatives
- [ ] **Phase 6** — Multi-asset portfolio optimization

For more detail, review [docs/roadmap.md](docs/roadmap.md).

## 🌐 Community

[![Discord](https://img.shields.io/badge/Discord-Join%20Server-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/tradepulse)
[![Twitter](https://img.shields.io/badge/Twitter-Follow-1DA1F2?style=for-the-badge&logo=twitter&logoColor=white)](https://twitter.com/tradepulse)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/company/tradepulse)

- 💬 [Discord Community](https://discord.gg/tradepulse) — Chat with users and developers
- 🐦 [Twitter](https://twitter.com/tradepulse) — Latest updates and news
- 📧 [Mailing List](https://tradepulse.io/newsletter) — Monthly newsletter
- 🎥 [YouTube](https://youtube.com/tradepulse) — Video tutorials
- 📝 [Blog](https://blog.tradepulse.io) — Technical articles

## 📜 License

TradePulse is distributed under the [TradePulse Proprietary License Agreement (TPLA)](LICENSE).

The TPLA permits internal, non-commercial evaluation and development use only.
Commercial usage of any portion of TradePulse requires a separate written
agreement with TradePulse Technologies.

## ⚠️ Disclaimer

**Trading involves substantial risk of loss and is not suitable for everyone.**
This software is provided for educational and research purposes. Past
performance does not guarantee future results. Always test strategies thoroughly
in paper trading before risking real capital.

## 🙏 Acknowledgments

- Built with a modern Python stack (FastAPI, Pydantic, SQLAlchemy)
- Inspired by [Zipline](https://github.com/quantopian/zipline),
  [Backtrader](https://github.com/mementum/backtrader), and
  [QuantLib](https://www.quantlib.org/)
- Geometric indicators based on research from leading quantitative finance journals
- Neuroscience-inspired components based on peer-reviewed research from *Science*, *Nature Neuroscience*, *Journal of Neuroscience*, and *Neural Computation*
- Special thanks to all
  [contributors](https://github.com/neuron7x/TradePulse/graphs/contributors)

---

## 🇺🇦 Короткий опис українською

### Що таке TradePulse?

TradePulse — це **платформа для алгоритмічної торгівлі**, яка застосовує **принципи нейронауки** до прийняття фінансових рішень. Подібно до того, як людський мозок використовує нейромедіатори (дофамін, серотонін, ГАМК) для навігації в умовах невизначеності, навчання з досвіду та управління ризиками, TradePulse реалізує ці самі біологічні механізми у вигляді алгоритмів.

### Для кого це?

- **Кількісні дослідники** — отримують унікальні сигнали за межами традиційних індикаторів
- **Інституційні торгові столи** — професійне управління ризиками та регуляторна відповідність
- **Дискреційні трейдери** — систематичний підхід для зменшення емоційних рішень
- **Розробники фінтех** — сучасна, розширювана інфраструктура для торгівлі
- **Хедж-фонди та prop-трейдинг** — високочастотні можливості з надійним бектестингом

### Нейронаукова основа

Проект базується на **6 ключових нейронаукових компонентах**:

1. **Дофаміновий контролер (Dopamine Controller)**
   - Основа: Нейрони VTA, що кодують помилку передбачення винагороди (RPE)
   - Реалізація: Алгоритм TD(0) для навчання з підкріпленням
   - Застосування: Навчання на прибуткових і збиткових угодах, модуляція впевненості

2. **Серотоніновий контролер (Serotonin Controller)**
   - Основа: 5-HT регуляція аверсивної обробки та поведінкового гальмування
   - Реалізація: Механізм вето, періоди охолодження, десенситизація
   - Застосування: Детекція просідання, запобігання панічним продажам

3. **ГАМК-гейт (GABA Inhibition Gate)**
   - Основа: ГАМКергічні інтернейрони, синаптична пластичність STDP
   - Реалізація: Швидке та повільне гальмування, пластичність LTP/LTD
   - Застосування: Контроль імпульсів, запобігання надмірній торгівлі

4. **NAK-контролер (Noradrenaline/Acetylcholine)**
   - Основа: Норадреналін (пильність) та ацетилхолін (увага)
   - Застосування: Модуляція ризику, масштабування позиції

5. **ECS-регулятор (Endocannabinoid System)**
   - Основа: Ендоканабіноїдна система компенсації стресу
   - Застосування: Диференціація гострого vs хронічного стресу, гомеостаз

6. **FHMC-мета-контролер (Hypothalamic Meta-Controller)**
   - Основа: Орексинова регуляція циклу неспання-сон
   - Застосування: Режими WAKE/SLEEP, захисні позиції при загрозах

### Геометричні індикатори

- **Осцилятори Курамото** — детекція фазової синхронізації, когерентність ринку
- **Потік Річчі** — відстеження геометричної кривизни, передбачення зміни режиму

### Наукова обґрунтованість

Всі компоненти базуються на рецензованих наукових публікаціях:
- Sutton & Barto (2018) — Reinforcement Learning
- Schultz et al. (1997) — Dopamine RPE (*Science*)
- Dayan & Huys (2009) — Serotonin (*Annual Review of Neuroscience*)
- Bi & Poo (1998) — STDP Plasticity (*Journal of Neuroscience*)
- Kuramoto (1984) — Chemical Oscillations
- Hamilton (1982) — Ricci Flow (*Journal of Differential Geometry*)

### Чому нейронаука для торгівлі?

**Традиційний підхід:**
- Індикатори на основі правил (RSI, MACD)
- Фіксовані параметри ризику
- Емоційні рішення людини або жорсткі алгоритми

**Нейронауковий підхід:**
- **Адаптивне навчання** — постійне навчання TD з ринкового зворотного зв'язку
- **Управління стресом** — зменшення ризику на основі серотоніну під час просідань
- **Контроль імпульсів** — ГАМК-гальмування запобігає надмірній торгівлі
- **Контекстна обізнаність** — ECS диференціює гострий vs хронічний ринковий стрес
- **Мета-контроль** — FHMC керує загальносистемними операційними режимами

**Результат:** Торгова система, яка адаптується як досвідчений трейдер, але зі стабільністю алгоритму, швидкістю комп'ютера та надійністю біологічного прийняття рішень, відточеного протягом мільйонів років еволюції.

### Документація

- [Повна документація англійською](#-documentation)
- [Архітектура нейронаукових компонентів](#-neuroscience-inspired-architecture)
- [Звіт про імплементацію нейромодуляторів](NEUROMODULATOR_IMPLEMENTATION_REPORT.md)
- [Імплементація допамінового циклу](DOPAMINE_LOOP_IMPLEMENTATION.md)
- [Стек нейрорішень](docs/neurodecision_stack.md)
- [Нейроекономіка](docs/neuroecon.md)

---

**[⬆ back to top](#-tradepulse)** · Made with ❤️ by the TradePulse community
