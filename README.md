# TradePulse

<a href="https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml"><img src="https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml/badge.svg"></a>
<a href="https://github.com/neuron7x/TradePulse/actions/workflows/security.yml"><img src="https://github.com/neuron7x/TradePulse/actions/workflows/security.yml/badge.svg"></a>

**Advanced algorithmic trading framework powered by geometric market indicators**

[![Tests Status](https://img.shields.io/github/actions/workflow/status/neuron7x/TradePulse/tests.yml?branch=main&label=tests)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)
[![Security Scan](https://img.shields.io/github/actions/workflow/status/neuron7x/TradePulse/security.yml?branch=main&label=security)](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/neuron7x/TradePulse/branch/main/graph/badge.svg)](https://codecov.io/gh/neuron7x/TradePulse)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)
[![Async: asyncio](https://img.shields.io/badge/async-asyncio-green.svg)](https://docs.python.org/3/library/asyncio.html)
[![Metrics: Prometheus](https://img.shields.io/badge/metrics-Prometheus-orange.svg)](https://prometheus.io/)

TradePulse is a professional algorithmic trading platform that combines advanced mathematical indicators (Kuramoto synchronization, Ricci curvature, entropy metrics) with modern backtesting and execution capabilities. The framework emphasizes geometric and topological market analysis to detect regime transitions and generate trading signals with confidence.

---

## 📚 Table of Contents

- [Overview](#-overview)
- [Continuous Integration & Quality](#-continuous-integration--quality)
- [Release Automation](#-release-automation)
- [Quick Start](#-quick-start)
- [Feature Highlights](#-feature-highlights)
- [Documentation](#-documentation)
- [Usage Examples](#-usage-examples)
- [Testing](#-testing)
- [Architecture](#-architecture)
- [Security](#-security)
- [Monitoring](#-monitoring)
- [Contributing](#-contributing)
- [License](#-license)
- [Acknowledgments](#-acknowledgments)
- [Contact](#-contact)

---

## 🔍 Overview

TradePulse delivers end-to-end tooling for quantitative research teams:

- High-fidelity indicators derived from differential geometry and dynamical systems.
- Walk-forward backtesting and live execution loops powered by async pipelines.
- GPU-accelerated performance primitives and observability baked in.
- A cross-language architecture spanning Python and Go for mission-critical workloads.

Whether you are prototyping strategies or orchestrating production trading bots, TradePulse provides production-ready scaffolding that remains flexible for experimentation.

> **Production status:** TradePulse is suitable for research, experimentation, and GitHub releases, but it is **not** ready for production live trading yet. Review the [Production Readiness Assessment](docs/production-readiness.md) for the outstanding work on live execution, exchange integrations, real-market testing, risk controls, documentation, and dashboards before considering deployment.

---

## ✅ Continuous Integration & Quality

| Signal | Description |
| --- | --- |
| [![Tests Status](https://img.shields.io/github/actions/workflow/status/neuron7x/TradePulse/tests.yml?branch=main&label=tests)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml) | Pytest suite covering unit, integration, async, fuzz and property-based checks. |
| [![Coverage](https://img.shields.io/codecov/c/github/neuron7x/TradePulse?branch=main&label=coverage)](https://app.codecov.io/gh/neuron7x/TradePulse) | Codecov uploads the latest coverage.xml artifact from CI for transparent coverage tracking. |
| [![Security Scan](https://img.shields.io/github/actions/workflow/status/neuron7x/TradePulse/security.yml?branch=main&label=security)](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml) | Automated secret detection, dependency auditing, and supply-chain checks. |

## 📦 Release Automation

TradePulse relies on [Release Drafter v6](https://github.com/release-drafter/release-drafter) to generate GitHub release drafts whenever commits land on `main`.

- **Triggering** – the workflow runs on every push to `main` and can be re-run manually via `workflow_dispatch`. Use the `force-refresh` input set to `true` when you need to rebuild the draft after re-tagging or relabeling pull requests.
- **Semantic labels** – pull requests tagged with `feature`, `bug`, or `chore` are automatically grouped into feature, fix, and maintenance sections. Additional labels `breaking`, `semver:major`, `semver:minor`, and `semver:patch` influence the semantic version that the resolver proposes.
- **Autolabeler sync** – the Release Drafter autolabeler heuristics add semantic labels based on branch prefixes (`feature/`, `hotfix/`) and pull-request titles that start with `feat`, `fix`, or `chore`. Adjust these rules inside `.github/release-drafter.yml` if your workflow conventions change.
- **Token permissions** – the workflow operates with the minimal permissions needed: `contents: write` and `pull-requests: write`. No `pull_request_target` triggers are used, so there are no security warnings about elevated contexts.
- **Caching & metrics** – the workflow fetches the full git history (tags included) so version resolution has access to previous releases. The summary posted to the GitHub run contains start/finish timestamps, total processed pull requests, and the generated draft URL for quick validation.

> 🔄 **Dry run tip:** Create a throwaway tag (for example `git tag -a v0.0.0-test -m "Release drafter dry run" && git push origin v0.0.0-test`) and dispatch the workflow with `force-refresh=true` to validate the output without affecting production releases. Delete the tag afterwards (`git push origin :refs/tags/v0.0.0-test`).

### Example draft body

```
## 🚀 Highlights
- New GPU-accelerated portfolio optimizer @octo-quants (#432)
- Fix execution gateway retries @qa-team (#433)

## 🔖 Release metadata
- Release: v2.2.0
- Previous tag: v2.1.3
- Next semantic target: v2.1.4 / v2.2.0 / v3.0.0

## 🙌 Contributors
- @octo-quants
- @qa-team
```

The generated release notes are subsequently copied into the curated [`CHANGELOG.md`](CHANGELOG.md) after validation.

Additional badges above surface Python support, static analysis (ruff, mypy), and observability integrations (Prometheus). For deeper insight into release readiness, review [`reports/`](reports/) for CI health, security posture, and technical debt snapshots.

---

## 🚀 Quick Start

### Installation with `pip`

```bash
# Clone the repository
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install runtime dependencies (use the lock file for reproducibility)
pip install -r requirements.lock

# Install development & test tooling (extends the runtime lock)
pip install -r requirements-dev.lock

# Optional extras (install only what you need)
# pip install ".[connectors]"  # market & broker integrations
# pip install ".[gpu]"         # GPU acceleration backends
# pip install ".[docs]"        # documentation toolchain
```

### Installation with Docker

```bash
# Build and start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

See the [Docker Quick Start Guide](docs/docker-quickstart.md) for detailed instructions, including GPU setup and troubleshooting tips.

---

## 🌟 Feature Highlights

### Advanced Indicators
- **Kuramoto Synchronization**: Phase coherence analysis for market synchronization detection.
- **Ricci Curvature**: Geometric curvature analysis on price graphs for regime detection.
- **Entropy Metrics**: Shannon entropy and delta entropy for market uncertainty quantification.
- **Hurst Exponent**: Long-memory process detection and trend persistence analysis.
- **VPIN (Volume-Synchronized Probability of Informed Trading)**: Order flow toxicity metrics.

### Trading Capabilities
- **Walk-forward Backtesting**: Realistic simulation with configurable windows.
- **Risk Management**: Position sizing, stop-loss, take-profit automation.
- **Multi-strategy Support**: Genetic algorithm-driven strategy optimization.
- **Async Data Ingestion**: Full async/await support for CSV and streaming data.
- **Real-time Execution**: Live trading interface with multiple data sources.

### Observability & Operations
- **Structured JSON Logging**: Correlation IDs, operation tracking, hierarchical logging.
- **Prometheus Metrics**: Complete instrumentation of features, backtests, data pipelines.
- **Performance Profiling**: Automatic execution time tracking for critical functions.
- **JSON Schemas**: Auto-generated schemas for public payloads (OpenAPI compatible).
- **Security Scanning**: Automated secret detection and dependency vulnerability checks.
- **Type Safety**: Strict mypy validation across Python modules.

### Streaming & Messaging
- **Schema Registry**: Versioned Avro/Protobuf contracts for ticks, bars, signals, orders, and fills with automated backward/forward compatibility checks.
- **Type Generation**: Build-time generation of Python (`core/events/models.py`) and TypeScript (`ui/dashboard/src/types/events.ts`) types from canonical schemas.
- **Event Bus**: Kafka/NATS abstractions with per-symbol partitioning, at-least-once delivery, idempotent processing, retry queues, and dead-letter routing.

### Performance Optimization
- **Float32 Precision**: 50% memory reduction with minimal accuracy loss.
- **Chunked Processing**: Efficiently handle unlimited dataset sizes.
- **GPU Acceleration**: CuPy integration for phase computation (5-50x speedup).
- **Memory Profiling**: Built-in tools for identifying memory bottlenecks.
- **Production Ready**: Optimized for large-scale data processing.

### Architecture Principles
- **Contracts-first Design**: Protocol Buffers for all data interfaces.
- **Fractal Modular Architecture (FPM-A)**: Clean separation of concerns.
- **Microservices Ready**: Go engines for performance-critical components.
- **Python Execution Loop**: Flexible strategy development and backtesting.

---

## 📖 Documentation

### Getting Started
- [Quick Start Guide](docs/quickstart.md) – Get up and running in minutes.
- [Installation Guide](docs/installation.md) – Prerequisites, supported platforms, virtualenv setup, extras, and dependency troubleshooting.
- [Architecture Overview](docs/ARCHITECTURE.md) – System design and principles.
- [Roadmap](docs/roadmap.md) – Development map aligned with quarterly goals.
- [FAQ](docs/faq.md) – Frequently asked questions.
- [Troubleshooting](docs/troubleshooting.md) – Common issues and solutions.

### Core Documentation
- [Indicators](docs/indicators.md) – Mathematical indicators and their usage.
- [Backtesting](docs/backtest.md) – Walk-forward simulation and testing.
- [Execution](docs/execution.md) – Order execution and risk management.
- [Agent System](docs/agent.md) – Genetic algorithm strategy optimization.
- **[Performance Guide](docs/performance.md)** – Optimization techniques and best practices.

### Developer Guides
- [Contributing](CONTRIBUTING.md) – Contribution guidelines and workflow.
- [Testing Guide](TESTING.md) – Comprehensive testing documentation.
- [Extending TradePulse](docs/extending.md) – Adding new indicators and strategies.
- [Integration API](docs/integration-api.md) – API reference and integration patterns.
- [Developer Scenarios](docs/scenarios.md) – Common development tasks.

### Operations
- [Security Policy](SECURITY.md) – Security guidelines and vulnerability reporting.
- [Monitoring Guide](docs/monitoring.md) – Metrics, logging, and alerting.
- [Deployment Guide](docs/deployment.md) – Infrastructure requirements, live runner configuration, secret management, and rollback playbooks.

---

## 🛠️ Usage Examples

### Analyze Market Data

```bash
# Analyze CSV data
python -m interfaces.cli analyze --csv sample.csv --window 200

# Output includes Kuramoto order, entropy, Ricci curvature, Hurst exponent
```

### Run Backtest

```bash
# Walk-forward backtest with custom strategy
python -m interfaces.cli backtest --csv sample.csv \
    --train-window 500 --test-window 100 \
    --initial-capital 10000
```

### Performance-Optimized Processing

```python
import numpy as np
from core.indicators.entropy import EntropyFeature
from core.indicators.hurst import HurstFeature
from core.data.preprocess import scale_series

# Large dataset (1M points)
large_data = np.random.randn(1_000_000)

# Memory-efficient processing with float32 (50% memory savings)
entropy_feat = EntropyFeature(
    bins=50,
    use_float32=True,
    chunk_size=100_000,
)

# Compute indicators
result = entropy_feat.transform(large_data)
print(f"Entropy: {result.value:.4f}")

# Scale data efficiently
scaled = scale_series(large_data, use_float32=True)

# See docs/performance.md for the complete guide
```

### Live Trading (Demo)

```bash
# Simulate live trading from CSV
python -m interfaces.cli live --source csv --path sample.csv --window 200
```

### Streamlit Dashboard

TradePulse includes a web-based dashboard built with Streamlit for real-time market analysis visualization.

#### Authentication Setup

The dashboard requires authentication for security. Configure credentials via environment variables:

```bash
# 1. Copy the example environment file
cp .env.example .env

# 2. Generate a secure password hash (example using Python)
python -c "import bcrypt; print(bcrypt.hashpw('your_secure_password'.encode(), bcrypt.gensalt()).decode())"

# 3. Update .env with your credentials
# DASHBOARD_ADMIN_USERNAME=admin
# DASHBOARD_ADMIN_PASSWORD_HASH=<your_generated_hash>
# DASHBOARD_COOKIE_KEY=<generate_random_key>  # e.g., python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### Running the Dashboard

```bash
# Install Streamlit dependencies (if not already installed)
pip install -c constraints/security.txt -r requirements.txt

# Run the dashboard
streamlit run interfaces/dashboard_streamlit.py

# The dashboard will open at http://localhost:8501
# Login with the credentials configured in .env
```

**Default credentials (development only):**
- Username: `admin`
- Password: `admin123` (⚠️ Change this in production!)

**Security Notes:**
- Never commit `.env` files to version control
- Always use strong passwords in production
- Generate unique cookie keys for each environment
- Password hashes are stored using bcrypt for security

See [Usage Examples](docs/examples/) and [Performance Demo](examples/performance_demo.py) for more detailed examples.

---

## 🧪 Testing

TradePulse relies on an extensive pytest testbed covering unit, integration, property-based, async, fuzz, and performance scenarios. The latest results and coverage are always available from the CI badges above, and full reports (HTML coverage, `coverage.xml`) are attached to each successful build.

### Quick Commands

```bash
# Run all tests
pytest tests/

# Run with branch coverage and HTML report
pytest tests/ --cov=core --cov=backtest --cov=execution --cov=analytics --cov-branch \
  --cov-report=xml --cov-report=term-missing --cov-report=html:coverage_html

# Skip slow tests during development
pytest tests/ -m "not slow"

# Run only property-based tests
pytest tests/property/

# Run only integration tests
pytest tests/integration/

# Run the replayable live-sim end-to-end pipeline test
pytest tests/integration/test_e2e_replay_live_sim.py -m integration -q

# Run quarantined flaky tests with automatic reruns
pytest tests/ -m flaky --reruns=2 --reruns-delay=2 \
  --flaky-report=reports/flaky-tests.json
```

Refer to [TESTING.md](TESTING.md) and [TESTING_SUMMARY.md](TESTING_SUMMARY.md) for deeper insights into coverage targets, fixtures, and workflow integration.

---

## 🧱 Architecture

```
TradePulse/
├── core/               # Core trading logic
│   ├── indicators/     # Mathematical indicators
│   ├── agent/          # Strategy optimization
│   ├── data/           # Data ingestion and preprocessing
│   └── phase/          # Market regime detection
├── backtest/           # Backtesting engine
├── execution/          # Order execution and risk management
├── interfaces/         # CLI and API interfaces
├── markets/            # Market-specific engines (Go)
│   ├── vpin/           # VPIN calculator
│   └── orderbook/      # Order book analyzer
├── analytics/          # Analytics engines (Go)
│   ├── fpma/           # FPM-A complexity analyzer
│   └── regime/         # Regime detection service
├── apps/               # Web applications
│   └── web/            # Next.js dashboard
└── docs/               # Documentation
```

Dive deeper with the dedicated [architecture diagram suite](docs/architecture/system_overview.md) covering the rendered system context, component interaction sequence, and governance data flows. The [feature store architecture breakdown](docs/architecture/feature_store.md) complements these visuals with detailed retention and materialisation internals.

---

## 🔐 Security

TradePulse takes security seriously. Please see [SECURITY.md](SECURITY.md) for:
- Vulnerability disclosure process
- Security best practices
- Dependency management
- Security tooling and scanning

---

## 📈 Monitoring

The framework includes built-in monitoring capabilities:
- Prometheus metrics export
- Structured logging
- Alert definitions for critical events
- Grafana dashboard templates

See the [Monitoring Guide](docs/monitoring.md) for setup and configuration details.

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development workflow
- Code standards
- PR and issue templates
- Review checklists

---

## 📄 License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Kuramoto Model**: Y. Kuramoto for synchronization theory
- **Ricci Curvature**: Geometric approaches to network analysis
- **VPIN**: Easley, López de Prado, and O'Hara for order flow toxicity metrics

---

## 📞 Contact

- **Issues**: [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- **Security**: security@tradepulse.local
- **General**: See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

**TradePulse** – готово до GitHub: лінт, тести, CI | Ready for production: linted, tested, CI/CD
