# 📈 TradePulse

### *Advanced Algorithmic Trading Framework with Geometric Market Indicators*

---

```ascii
╔═══════════════════════════════════════════════════════════╗
║ 🎯 Enterprise-Grade Trading • 🧮 Geometric Indicators       ║
║ ⚡ Real-Time Analytics • 🔒 Production-Ready Security       ║
╚═══════════════════════════════════════════════════════════╝
```

TradePulse is a **production-grade algorithmic trading platform** that marries
cutting-edge geometric market indicators with enterprise reliability.
Quantitative researchers, discretionary traders, and financial institutions use
TradePulse to move from research to live execution with confidence.

## Table of Contents

- [Why TradePulse?](#-why-tradepulse)
- [Feature Highlights](#-feature-highlights)
- [Quick Start](#-quick-start)
- [Demo Dashboard](#-demo-dashboard)
- [System Architecture](#-system-architecture)
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

## 🎯 Why TradePulse?

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
- **Risk Management** — pre-trade checks and configurable limits
- **Paper Trading** — safe deployment dry runs
- **Canary Releases** — progressive rollout tooling
- **Circuit Breakers** — automatic fault protection

### 🔒 Enterprise Security
- **HashiCorp Vault** — centralized secret management
- **Role-Based Access Control** — granular permissions
- **Audit Logging** — full compliance traceability
- **Encrypted Storage** — end-to-end protection
- **MiFID II Compliance** — regulatory readiness

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

## 🚀 Quick Start

### Installation

```bash
# Install with pip
pip install tradepulse

# With optional dependencies
pip install "tradepulse[connectors,feature_store,gpu]"

# From source
git clone https://github.com/your-org/tradepulse.git
cd tradepulse
pip install -e ".[dev]"
```

### Developer Environment

```bash
# Bootstrap linting and security hooks
pipx install pre-commit
pre-commit install

# Run the full hook suite before pushing
pre-commit run --all-files

# Type-check and test with coverage guarantees (>=85%)
pytest -q --maxfail=1 --disable-warnings --cov=. --cov-report=xml

# Install JavaScript tooling (respects root tsconfig + ESLint policies)
npm install
npx eslint . --ext .ts,.tsx

# Verify Go packages using the stricter golangci-lint gate
golangci-lint run
```

### Container Image

```bash
# Build the hardened runtime image with BuildKit caching
DOCKER_BUILDKIT=1 docker build -t tradepulse:dev .

# Execute the healthcheck locally (mirrors CI container scan job)
docker run --rm tradepulse:dev python healthcheck.py
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

### Secrets & Environment Management

- Copy [`.env.example`](.env.example) to `.env` for local development and populate only the values you require.
- Never commit `.env` files — they are ignored by git and intended for workstation-only secrets.
- Production deployments must source secrets from a vault (HashiCorp Vault, AWS Secrets Manager, or GCP Secret Manager).
- See [`application/settings.py`](application/settings.py) for environment variable contracts and [`SECURITY.md`](SECURITY.md) for rotation SLAs.
- Rotate leaked credentials immediately and document the rotation in the [CHANGELOG](CHANGELOG.md) under the 🔐 Security section.

For HashiCorp Vault, provide a resolver path via the `TRADEPULSE_VAULT_PATH` environment variable or the CLI:

```bash
# Authenticate to Vault and inject secrets for the live runner
vault login
python -m scripts.cli secrets-issue-dynamic \
  --address https://vault.example:8200 \
  --role tradepulse-live \
  --mount database \
  --output .secrets/live-runner.json
```

For cloud secret managers, update `deploy-environments.yml` with the ARN/ID of the secret and set the corresponding `*_VAULT_PATH` variable in CI.

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
git clone https://github.com/your-org/tradepulse.git
cd tradepulse
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

TradePulse is released under the [MIT License](LICENSE).

```
MIT License

Copyright (c) 2025 TradePulse Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```

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
- Special thanks to all
  [contributors](https://github.com/your-org/tradepulse/graphs/contributors)

---

**[⬆ back to top](#-tradepulse)** · Made with ❤️ by the TradePulse community

---

## NeuroTrade PRO v1.2 — Integrated Neuro–AI Stack + SABRE Conformal Action Layer

**Що всередині:**
- Режими ринку (волатильнісні біни) → режимно-чутливе рішення
- Квантильні моделі (L/M/U) → **Conformal (CQR) з експон. вагами + динамічна α**
- **SABRE CAL**: дія лише коли нижня (або верхня) межа після витрат > 0
- Execution: fee, half-spread, **impact (linear / quadratic / square_root)**, базовий queue-fill
- Мікроструктура: spread, eff/realized spread, OFI (short-horizon), signed vol, Kyle λ, vol-of-vol, VWAP-dist, fracdiff
- Risk guardrails: DD ліміт, cooldown, vola-throttle, exposure cap
- CV: Purged & Embargoed K-Fold; Labeling: triple-barrier (приклад)
- Оцінка: Sharpe, Deflated Sharpe (approx), CVaR
- Моніторинг: **Logger** (MLflow/W&B якщо доступно), інакше no-op
- **Walk-Forward** (серійний/паралельний), **Validate** (порівняння з baseline, coverage, capacity)

### Швидкий старт
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/make_synth.py
python scripts/run_backtest.py --config configs/demo.yaml
python scripts/run_walkforward.py --config configs/wf.yaml

# Повна валідація
python scripts/validate.py --config configs/demo.yaml
```

### Примітки

* Для моніторингу:
  * MLflow: `export MLFLOW_TRACKING_URI=file:./mlruns` та (опц.) `MLFLOW_EXPERIMENT_NAME=neurotrade_v12`
  * W&B: `export WANDB_API_KEY=...` і `WANDB_PROJECT=neurotrade_v12`
* **Не плутати** CAL із самою альфою: CAL — *safety layer* над будь-якою моделлю.
