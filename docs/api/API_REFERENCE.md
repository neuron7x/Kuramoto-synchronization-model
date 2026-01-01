---
owner: integrations@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse SDK API Reference

> **Version**: 0.1.0  
> **Last Updated**: 2024-12-01

This document provides comprehensive API documentation for the TradePulse SDK,
including both the core Trading SDK and the MLSDM (Multi-Level Stochastic
Decision Model) SDK.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Trading SDK](#trading-sdk)
  - [TradePulseSDK](#tradepulsesdk)
  - [Data Contracts](#data-contracts)
- [MLSDM SDK](#mlsdm-sdk)
  - [Entry Points](#entry-points)
  - [MLSDM Facade](#mlsdm-facade)
  - [FHMC Controller](#fhmc-controller)
  - [ActorCriticFHMC Agent](#actorcriticfhmc-agent)
  - [SleepReplayEngine](#sleepreplayengine)
  - [CFGWO Optimizer](#cfgwo-optimizer)
  - [Configuration](#configuration)
  - [Data Contracts](#mlsdm-data-contracts)
- [CLI Reference](#cli-reference)
- [HTTP API](#http-api)

---

## Overview

The TradePulse SDK provides two main modules:

1. **Trading SDK**: Core trading operations including signal generation,
   order proposals, risk checks, and execution.

2. **MLSDM SDK**: Adaptive decision-making with neuro-inspired components:
   - **FHMC**: Fracto-Hypothalamic Meta-Controller for timing decisions
   - **ActorCriticFHMC**: RL agent with biomarker feedback
   - **SleepReplayEngine**: Priority replay buffer with dream-like regeneration
   - **CFGWO**: Chaotic Fractal Grey Wolf Optimizer

---

## Installation

```bash
pip install tradepulse
```

For MLSDM features with GPU support:

```bash
pip install tradepulse[gpu]
```

---

## Quick Start

### Trading SDK

```python
from tradepulse.sdk import TradePulseSDK, MarketState, SDKConfig
from application.system import TradePulseSystem

# Initialize system
system = TradePulseSystem(config)

# Configure SDK
config = SDKConfig(
    default_venue="binance",
    signal_strategy=my_strategy,
    position_sizer=my_position_sizer,
)

# Create SDK instance
sdk = TradePulseSDK(system, config)

# Generate signal and execute trade
state = MarketState(symbol="BTCUSDT", venue="BINANCE", market_frame=df)
signal = sdk.get_signal(state)
proposal = sdk.propose_trade(signal)
risk_result = sdk.risk_check(proposal.order)
if risk_result.approved:
    result = sdk.execute(proposal.order)
```

### MLSDM SDK

```python
from tradepulse.sdk.mlsdm import MLSDM, create_fhmc, create_agent

# Quick start with defaults
mlsdm = MLSDM.default()

# Get biomarker state
biomarkers = mlsdm.get_biomarkers()
print(f"Orexin: {biomarkers.orexin:.3f}, Threat: {biomarkers.threat:.3f}")

# Compute drive from market conditions
biomarkers = mlsdm.compute_drive(
    exp_return=0.05,
    novelty=0.3,
    load=0.2,
    maxdd=0.1,
    volshock=0.5,
    cp_score=0.2,
)

# Get adaptive window for next decision
window = mlsdm.next_window()
print(f"Next decision window: {window:.1f} seconds")
```

---

## Trading SDK

### TradePulseSDK

The main orchestration class for trading operations.

```python
class TradePulseSDK:
    """Orchestrate trading operations via the public SDK contract."""

    def __init__(self, system: TradePulseSystem, config: SDKConfig) -> None:
        """Initialize the SDK.

        Args:
            system: TradePulse system instance.
            config: SDK configuration.
        """

    def get_signal(self, market_state: MarketState) -> Signal:
        """Derive a trading signal for the supplied market state.

        Args:
            market_state: Market state container with price data.

        Returns:
            Signal with action (BUY, SELL, EXIT, HOLD) and confidence.

        Raises:
            ValueError: If no signals generated.
        """

    def propose_trade(self, signal: Signal) -> SuggestedOrder:
        """Produce an order proposal for a signal.

        Args:
            signal: Trading signal to convert to order.

        Returns:
            SuggestedOrder with order details and session ID.

        Raises:
            LookupError: If no market context for symbol.
            ValueError: If signal is HOLD or position is invalid.
        """

    def risk_check(self, order: Order) -> RiskCheckResult:
        """Run the core risk controls against an order.

        Args:
            order: Order to validate.

        Returns:
            RiskCheckResult with approval status and reason.
        """

    def execute(self, order: Order) -> ExecutionResult:
        """Submit an order to the execution loop.

        Args:
            order: Order to execute.

        Returns:
            ExecutionResult with correlation ID and venue.

        Raises:
            RuntimeError: If order failed risk validation.
        """

    def get_audit_log(self, session_id: str) -> tuple[AuditEvent, ...]:
        """Return the immutable audit trail for a session."""
```

### Data Contracts

#### MarketState

```python
@dataclass(slots=True)
class MarketState:
    """Container describing the observable market environment."""
    symbol: str
    venue: str
    market_frame: pd.DataFrame
    strategy: Callable[[np.ndarray], np.ndarray] | None = None
```

#### SDKConfig

```python
@dataclass(slots=True)
class SDKConfig:
    """Runtime configuration for TradePulseSDK."""
    default_venue: str
    signal_strategy: Callable[[np.ndarray], np.ndarray]
    position_sizer: Callable[[Signal], float]
    venue_overrides: Mapping[str, str] = field(default_factory=dict)
    correlation_id_factory: Callable[[], str] = field(default_factory=_uuid_hex_factory)
    session_id_factory: Callable[[], str] = field(default_factory=_uuid_hex_factory)
```

---

## MLSDM SDK

### Entry Points

The MLSDM SDK exposes four primary entry points:

| Function | Description |
|----------|-------------|
| `create_fhmc()` | Create FHMC controller from config or YAML |
| `create_agent()` | Create ActorCriticFHMC RL agent |
| `create_optimizer()` | Create CFGWO optimizer |
| `create_replay_engine()` | Create SleepReplayEngine |

Additionally, the `MLSDM` facade class provides a unified interface.

### MLSDM Facade

```python
from tradepulse.sdk.mlsdm import MLSDM, MLSDMConfig

# Create from configuration file
mlsdm = MLSDM.from_config("config/mlsdm.yaml")

# Or use defaults
mlsdm = MLSDM.default()
```

#### Methods

```python
class MLSDM:
    """Unified facade for the Multi-Level Stochastic Decision Model."""

    @classmethod
    def from_config(cls, config: MLSDMConfig | str | Path) -> MLSDM:
        """Create MLSDM from configuration."""

    @classmethod
    def default(cls) -> MLSDM:
        """Create MLSDM with default configuration."""

    def get_biomarkers(self) -> BiomarkerState:
        """Get current biomarker state from FHMC."""

    def get_decision_state(self) -> DecisionState:
        """Get current decision state."""

    def update_biomarkers(
        self,
        actions: Iterable[float],
        latents: Iterable[float],
        *,
        fs_latents: int = 50,
    ) -> BiomarkerState:
        """Update biomarkers with new action and latent series."""

    def compute_drive(
        self,
        exp_return: float,
        novelty: float,
        load: float,
        maxdd: float,
        volshock: float,
        cp_score: float,
    ) -> BiomarkerState:
        """Compute orexin and threat from market conditions."""

    def act(self, state: np.ndarray) -> np.ndarray:
        """Select action using the RL agent."""

    def learn(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> TrainingStep:
        """Update agent with a single transition."""

    def observe(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        td_error: float,
        *,
        cp_score: float = 0.0,
        imminence_jump: float = 0.0,
    ) -> float:
        """Store a transition in the replay buffer."""

    def sample(self, batch_size: int = 64) -> list[ReplayTransition]:
        """Sample a batch of transitions from replay buffer."""

    def optimize(
        self,
        objective: Callable[[np.ndarray], float],
        dim: int,
        bounds: tuple[Sequence[float], Sequence[float]],
        *,
        config: OptimizerConfig | None = None,
    ) -> OptimizationResult:
        """Run CFGWO optimization."""

    def next_window(self) -> float:
        """Get the recommended window size for next decision."""
```

### FHMC Controller

The Fracto-Hypothalamic Meta-Controller manages adaptive decision timing.

```python
from tradepulse.sdk.mlsdm import create_fhmc, FHMCConfig

# From YAML file
fhmc = create_fhmc("config/fhmc.yaml")

# From configuration object
config = FHMCConfig(
    alpha_target=(0.5, 1.5),
    orexin={"k1": 1.0, "k2": 0.7, "k3": 0.3},
)
fhmc = create_fhmc(config)

# Default configuration
fhmc = create_fhmc()
```

#### FHMC Methods

| Method | Description |
|--------|-------------|
| `compute_orexin(exp_return, novelty, load)` | Compute arousal signal |
| `compute_threat(maxdd, volshock, cp_score)` | Compute threat signal |
| `flipflop_step()` | Update WAKE/SLEEP state |
| `next_window_seconds()` | Get adaptive time window |
| `update_biomarkers(actions, latents)` | Update from action/latent series |
| `threat_markers(returns)` | Compute threat markers from returns |
| `novelty_from_embeddings(graph, emb_i, emb_j)` | Compute novelty from embeddings |

### ActorCriticFHMC Agent

RL agent with FHMC biomarker feedback.

```python
from tradepulse.sdk.mlsdm import create_agent, create_fhmc

fhmc = create_fhmc()
agent = create_agent(
    state_dim=10,
    action_dim=3,
    fhmc=fhmc,
    config=AgentConfig(lr=1e-4, device="cuda"),
)

# Training loop
state = agent.reset()
for step in range(1000):
    action = agent.act(state)
    next_state, reward, done = env.step(action)
    agent.learn(state, action, reward, next_state, done)
    state = next_state
```

### SleepReplayEngine

Priority replay buffer with novelty-aware sampling.

```python
from tradepulse.sdk.mlsdm import create_replay_engine

engine = create_replay_engine(
    capacity=100_000,
    psi=0.5,      # Change-point weight
    phi=0.3,      # Imminence weight
    dgr_ratio=0.25,
)

# Store transitions
priority = engine.observe_transition(
    state=obs,
    action=action,
    reward=reward,
    next_state=next_obs,
    td_error=td_error,
    cp_score=0.3,
)

# Sample batch
batch = engine.sample(batch_size=64)
```

### CFGWO Optimizer

Chaotic Fractal Grey Wolf Optimizer for crisis adaptation.

```python
from tradepulse.sdk.mlsdm import create_optimizer

def objective(params):
    return np.sum((params - target) ** 2)

optimizer = create_optimizer(
    objective=objective,
    dim=5,
    bounds=([0, 0, 0, 0, 0], [1, 1, 1, 1, 1]),
    config=OptimizerConfig(
        pack=30,
        iters=300,
        chaos=True,
        fractal_step=True,
    ),
)

best_params, best_score = optimizer.optimize()
```

### Configuration

#### FHMCConfig

```python
@dataclass(slots=True)
class FHMCConfig:
    alpha_target: tuple[float, float] = (0.5, 1.5)
    orexin: dict[str, float]     # k1, k2, k3 weights
    threat: dict[str, float]     # w_dd, w_vol, w_cp weights
    flipflop: dict[str, float]   # theta_lo, theta_hi, omega_lo, omega_hi
    mfs: dict[str, Any]          # depth, p, heavy_tail, base_dt_seconds
    arousal: dict[str, Any]      # slope_gate
    sleep: dict[str, Any]        # dgr_ratio
    explore: dict[str, Any]      # ou_theta, ou_sigma
    fractional_update: dict[str, Any]  # eta_f, levy_alpha
```

#### MLSDMConfig

```python
@dataclass(slots=True)
class MLSDMConfig:
    fhmc: FHMCConfig
    agent: AgentConfig | None = None
    optimizer: OptimizerConfig | None = None
```

#### Example YAML Configuration

```yaml
# mlsdm_config.yaml
fhmc:
  alpha_target: [0.5, 1.5]
  orexin:
    k1: 1.0
    k2: 0.7
    k3: 0.3
  threat:
    w_dd: 0.5
    w_vol: 0.3
    w_cp: 0.2
    cp_threshold: 5.0
    vol_window: 60
  flipflop:
    theta_lo: 0.6
    theta_hi: 0.8
    omega_lo: 0.4
    omega_hi: 0.6
  mfs:
    depth: 12
    p: 0.6
    heavy_tail: 0.5
    base_dt_seconds: 60.0
    adapt_alpha: false
  arousal:
    slope_gate: false
  sleep:
    dgr_ratio: 0.25
  explore:
    ou_theta: 0.15
    ou_sigma: 0.3
    use_colored_noise_ppo: false
  fractional_update:
    eta_f: 0.5
    levy_alpha: 1.5

agent:
  state_dim: 10
  action_dim: 3
  lr: 0.0003
  device: cpu

optimizer:
  dim: 5
  pack: 20
  iters: 200
  chaos: true
  fractal_step: true
```

### MLSDM Data Contracts

#### BiomarkerState

```python
@dataclass(frozen=True, slots=True)
class BiomarkerState:
    """Biomarker readings from the FHMC controller."""
    orexin: float           # Arousal signal [0, 1]
    threat: float           # Threat signal [0, 1]
    state: str              # "WAKE" or "SLEEP"
    alpha_history: tuple[float, ...]  # DFA alpha values
    slope_history: tuple[float, ...]  # Aperiodic slopes
```

#### DecisionState

```python
@dataclass(frozen=True, slots=True)
class DecisionState:
    """Decision state for the MLSDM system."""
    free_energy: float
    baseline_free_energy: float
    latency_spike: float
    steps_in_crisis: int
    window_seconds: float
```

#### OptimizationResult

```python
@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Result of a CFGWO optimization run."""
    best_params: np.ndarray
    best_score: float
    iterations: int
    pack_size: int

    def to_dict(self) -> dict[str, object]:
        """Convert to JSON-serializable dictionary."""
```

#### ReplayTransition

```python
@dataclass(frozen=True, slots=True)
class ReplayTransition:
    """Experience transition from replay buffer."""
    state: np.ndarray
    action: np.ndarray
    reward: float
    next_state: np.ndarray
    priority: float
    cp_score: float
```

#### TrainingStep

```python
@dataclass(frozen=True, slots=True)
class TrainingStep:
    """Training step output from agent learning."""
    td_error: float
    orexin: float
    threat: float
    state: str
    timestamp: datetime
```

---

## CLI Reference

The TradePulse CLI provides commands for common workflows:

```bash
# Data ingestion
tradepulse_cli ingest --config ingest.yaml

# Run backtest
tradepulse_cli backtest --config backtest.yaml --output table

# Parameter optimization
tradepulse_cli optimize --config optimize.yaml

# FETE backtest
tradepulse_cli fete-backtest --csv data.csv --price-col price --out equity.csv

# Causal pipeline
tradepulse_cli causal-pipeline --returns-csv returns.csv --output result.json
```

For MLSDM-specific CLI commands, see the extended documentation.

---

## HTTP API

The TradePulse HTTP API is exposed via FastAPI. See `docs/api/` for OpenAPI
specifications and detailed endpoint documentation.

### Example Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/signals` | POST | Generate trading signals |
| `/api/v1/orders` | POST | Submit orders |
| `/api/v1/orders/{id}` | GET | Get order status |
| `/api/v1/mlsdm/biomarkers` | GET | Get current biomarkers |
| `/api/v1/mlsdm/action` | POST | Get MLSDM action recommendation |

---

## See Also

- [Architecture Documentation](../CORE_ARCHITECTURE_IMPLEMENTATION.md)
- [Neurodecision Stack](../docs/neurodecision_stack.md)
- [FHMC Demo Script](../scripts/run_fhmc_demo.py)
- [TradePulse CLI Reference](../docs/tradepulse_cli_reference.md)
