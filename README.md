# TradePulse

[![Tests Status](https://img.shields.io/github/actions/workflow/status/neuron7x/TradePulse/tests.yml?branch=main&label=tests)](https://github.com/neuron7x/TradePulse/actions/workflows/tests.yml)
[![Security Scan](https://img.shields.io/github/actions/workflow/status/neuron7x/TradePulse/security.yml?branch=main&label=security)](https://github.com/neuron7x/TradePulse/actions/workflows/security.yml)
[![Coverage](https://codecov.io/gh/neuron7x/TradePulse/branch/main/graph/badge.svg)](https://codecov.io/gh/neuron7x/TradePulse)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **TradePulse** is a research-focused algorithmic trading platform. It combines geometric market indicators, regime-aware agents, vectorised backtesting, execution simulators, and production runbooks so quantitative teams can move from exploration to live trading with traceability.

---

## 📚 Table of contents

1. [Platform overview](#-platform-overview)
2. [Key capabilities](#-key-capabilities)
3. [Architecture](#-architecture)
4. [Repository map](#-repository-map)
5. [Getting started](#-getting-started)
6. [CLI quick start](#-cli-quick-start)
7. [Python API example](#-python-api-example)
8. [Data & configuration](#-data--configuration)
9. [Quality & testing](#-quality--testing)
10. [Observability & operations](#-observability--operations)
11. [Deployment & infrastructure](#-deployment--infrastructure)
12. [Documentation guide](#-documentation-guide)
13. [Contributing & governance](#-contributing--governance)
14. [Community & support](#-community--support)
15. [License](#-license)
16. [Швидка довідка українською](#-швидка-довідка-українською)

---

## 🔍 Platform overview

TradePulse delivers an end-to-end toolkit for quantitative research and live trading:

- **Research pipelines** ingest multi-venue data, compute entropy, curvature, phase, and synchrony indicators, and orchestrate feature blocks documented across [`core/indicators`](core/indicators) and [`docs/indicators.md`](docs/indicators.md).
- **Backtesting & analytics** rely on deterministic walk-forward engines, stress harnesses, and reporting utilities in [`backtest/`](backtest), [`analytics/`](analytics), and [`reports/`](reports).
- **Execution surfaces** cover strategy agents, risk controls, order routing, and compliance tooling across [`core/agent`](core/agent), [`core/risk`](core/risk), [`execution/`](execution), and [`interfaces`](interfaces).
- **Operational tooling** spans observability, governance, and automation via [`observability/`](observability), [`scripts/`](scripts), [`docs/operational_handbook.md`](docs/operational_handbook.md), and related runbooks.
- **Cross-language accelerators** include the Rust crate at [`rust/tradepulse-accel`](rust/tradepulse-accel) and Go bindings declared in [`go.mod`](go.mod).

The documentation set in [`docs/`](docs) captures architecture, governance, incident response, and training programmes to keep the platform production ready.

---

## 🧠 Key capabilities

### Market & alternative data

- Ingestion layer at [`core/data`](core/data) with CSV guards, timestamp normalisation, and Binance streaming hooks.
- CLI and service adapters in [`interfaces/ingestion.py`](interfaces/ingestion.py) and [`interfaces/cli.py`](interfaces/cli.py) expose batch and live workflows.
- Dataset catalogues, retention policies, and governance templates live in [`docs/dataset_catalog.md`](docs/dataset_catalog.md) and [`schemas/`](schemas).

### Indicator & feature engineering

- Feature primitives (Kuramoto order, Ricci curvature, entropy, Hurst exponent) live in [`core/indicators`](core/indicators).
- Regime detection and phase transitions are implemented in [`core/phase`](core/phase) and orchestrated through [`core/agent`](core/agent).
- Composition patterns and mathematical context are detailed in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/FPM-A.md`](docs/FPM-A.md).

### Backtesting, analytics & reporting

- Deterministic walk-forward simulations, latency controls, and transaction cost models are implemented in [`backtest/engine.py`](backtest/engine.py) and [`backtest/transaction_costs.py`](backtest/transaction_costs.py).
- Exploratory notebooks, attribution reports, and scorecards use modules in [`analytics/`](analytics) and [`reports/`](reports).
- Cookbook workflows are documented in [`docs/scenarios.md`](docs/scenarios.md) and [`docs/cookbook_backtest_live.md`](docs/cookbook_backtest_live.md).

### Execution, risk & compliance

- Execution gateways, venue adapters, and orchestration live in [`execution/`](execution) and [`interfaces/live_runner.py`](interfaces/live_runner.py).
- Risk and compliance guardrails are centralised in [`core/risk`](core/risk), [`core/compliance`](core/compliance), and policy references such as [`docs/governance.md`](docs/governance.md).
- Automated agent scheduling, bandit coordination, and evaluation flows live in [`core/agent`](core/agent) with operational guardrails recorded in [`docs/agent.md`](docs/agent.md).

### Observability & operations

- Structured logging, metrics, and tracing utilities live in [`observability/`](observability) and [`core/utils/metrics.py`](core/utils/metrics.py).
- Production monitoring, SLO policies, and incident playbooks are captured in [`docs/monitoring.md`](docs/monitoring.md), [`docs/reliability.md`](docs/reliability.md), and [`docs/incident_playbooks.md`](docs/incident_playbooks.md).

### Interfaces & visualisation

- CLI orchestrations are exposed via [`interfaces/cli.py`](interfaces/cli.py) (documented in [`docs/tradepulse_cli_reference.md`](docs/tradepulse_cli_reference.md)).
- HTTP and secrets adapters live in [`interfaces/http`](interfaces/http) and [`interfaces/secrets`](interfaces/secrets).
- The modular ES module dashboard in [`ui/dashboard`](ui/dashboard) renders telemetry widgets with tests in [`ui/dashboard/tests`](ui/dashboard/tests).

---

## 🏗️ Architecture

TradePulse follows a layered, contracts-first architecture:

- **Domain layer**: canonical trading primitives in [`domain/`](domain) (`Order`, `Position`, `Signal`) that enforce invariants for upper layers.
- **Application layer**: orchestration services, DTO mappers, and workflow coordinators in [`application/`](application).
- **Core services**: indicator math, agent logic, compliance, messaging, and utilities in [`core/`](core).
- **Adapters & delivery**: CLI, HTTP, dashboards, and external integrations under [`interfaces/`](interfaces), [`ui/`](ui), and [`execution/`](execution).
- **Operational tooling**: automation scripts, infra-as-code, and observability surfaces in [`scripts/`](scripts), [`deploy/`](deploy), [`infra/`](infra), and [`observability/`](observability).

Architectural diagrams, sequence flows, and resilience blueprints are maintained in [`docs/architecture`](docs/architecture) and summarised in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🗂️ Repository map

| Path | Purpose |
| --- | --- |
| `analytics/` | Attribution studies, scenario analytics, and reporting helpers. |
| `application/` | Application services that orchestrate domain workflows. |
| `backtest/` | Simulation engine, transaction cost models, performance exports. |
| `configs/`, `conf/` | Runtime configuration templates and environment profiles. |
| `core/` | Indicator library, agents, compliance, risk, messaging, utilities. |
| `data/`, `sample.csv` | Reference datasets and fixtures for quick experiments. |
| `deploy/` | Kubernetes manifests, Kustomize overlays, and Prometheus config. |
| `docs/` | Authoritative documentation set (architecture, runbooks, policies). |
| `domain/` | Domain entities, aggregates, and invariants. |
| `execution/` | Order routing, broker adapters, and live orchestration. |
| `infra/` | Terraform blueprints and infrastructure automation. |
| `interfaces/` | CLI entrypoints, ingestion services, HTTP/gRPC facades. |
| `libs/` | Shared assets including protocol buffers and migration stubs. |
| `observability/` | Metrics, tracing, logging, and monitoring helpers. |
| `scripts/` | Automation utilities (data sanity checks, smoke test runners). |
| `stakeholders/` | Communication plans, RACI charts, and stakeholder manifests. |
| `strategies/` | Strategy templates, policy routing, and experimentation sandboxes. |
| `tests/` | Unit, integration, property, fuzz, contract, data, security, and E2E suites. |
| `ui/dashboard/` | Dashboard application code, styles, and tests. |

---

## 🚀 Getting started

### Requirements

- Python **3.11 or 3.12** with `pip` (other supported versions listed in [`pyproject.toml`](pyproject.toml)).
- Recommended tooling: `make`, `pre-commit`, Docker 24+, Node.js 18.18+ for the dashboard, and Redis/PostgreSQL for integration tests.
- Optional: Go 1.23+ and a Rust toolchain for the accelerator crate, GPU extras for CUDA-backed indicators.

### Local installation (pip)

```bash
# Clone the repository
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install runtime dependencies (locked for reproducibility)
pip install -r requirements.lock

# Install development and testing toolchain
pip install -r requirements-dev.lock

# Optional extras
pip install .[connectors]  # broker APIs and realtime feeds
pip install .[gpu]          # GPU acceleration backends
pip install .[docs]         # documentation build toolchain

# Enable lint/test hooks
pre-commit install
```

### Docker Compose quick start

```bash
docker compose up --build -d
# Exposes API, worker, and observability containers as defined in docker-compose.yml
```

---

## 🛠️ CLI quick start

The CLI is the operational entry point described in [`docs/quickstart.md`](docs/quickstart.md) and [`docs/tradepulse_cli_reference.md`](docs/tradepulse_cli_reference.md).

```bash
# Analyze the bundled sample.csv dataset
python -m interfaces.cli analyze --csv sample.csv --window 200 --price-col close

# Run a walk-forward backtest with indicator-derived signals
python -m interfaces.cli backtest \
    --csv sample.csv \
    --window 200 \
    --price-col close \
    --fee 0.0005

# Bootstrap a live trading harness with configuration overrides
python -m interfaces.cli live --config configs/live/default.toml
```

Configuration overrides can be injected through YAML files described in [`docs/scenarios.md`](docs/scenarios.md) and enforced by `core.data.path_guard` protections.

---

## 🧪 Python API example

```python
import numpy as np
import pandas as pd

from interfaces.cli import signal_from_indicators
from backtest.engine import walk_forward

prices = pd.read_csv("sample.csv")["close"].to_numpy(dtype=float)
signals = signal_from_indicators(prices, window=128)

result = walk_forward(
    prices,
    lambda _: signals,
    fee=0.0005,
    initial_capital=10_000.0,
    strategy_name="demo-indicator-stack",
)

print(f"Ending equity: {result.equity_curve[-1]:.2f}")
if result.performance:
    print(f"Annualised return: {result.performance.annualised_return:.2%}")
```

This mirrors the cookbook pipeline (ingest → indicators → backtest) documented in [`docs/quickstart.md`](docs/quickstart.md).

---

## 🗄️ Data & configuration

- Reference CSV fixtures live in [`data/`](data) with governance guardrails explained in [`docs/dataset_catalog.md`](docs/dataset_catalog.md).
- YAML/JSON configuration templates live under [`configs/`](configs) and [`conf/`](conf) for backtests, live runs, feature toggles, and secrets policies.
- Schema definitions for payloads, DTOs, and persisted artefacts live in [`schemas/`](schemas) with validation harnesses in [`tests/contracts`](tests/contracts).

---

## ✅ Quality & testing

- The testing strategy, coverage targets, and suite structure are documented in [`TESTING.md`](TESTING.md) and [`tests/TEST_PLAN.md`](tests/TEST_PLAN.md).
- Core commands:
  ```bash
  # Full suite with coverage
  pytest tests/ \
    --cov=core --cov=backtest --cov=execution \
    --cov-config=configs/quality/critical_surface.coveragerc \
    --cov-report=term-missing --cov-report=xml

  python -m tools.coverage.guardrail \
    --config configs/quality/critical_surface.toml \
    --coverage coverage.xml

  # Fast feedback loop
  make test:fast

  # Smoke the CLI workflows
  pytest tests/e2e/ -m "not slow and not flaky"
  ```
- Security, fuzz, and data-quality checks are located in [`tests/security`](tests/security), [`tests/fuzz`](tests/fuzz), and [`tests/data`](tests/data) with complementary automation in [`scripts/`](scripts).
- CI expectations include linting with Ruff and type-checking via MyPy (configured in [`pyproject.toml`](pyproject.toml)).

---

## 📈 Observability & operations

- Metrics exporters, tracing helpers, and logging policies live in [`observability/`](observability) and [`core/utils/metrics.py`](core/utils/metrics.py).
- Operational handbooks and incident playbooks: [`docs/operational_handbook.md`](docs/operational_handbook.md), [`docs/incident_playbooks.md`](docs/incident_playbooks.md), [`docs/runbook_live_trading.md`](docs/runbook_live_trading.md).
- SLO governance, cost controls, and resilience planning: [`docs/reliability.md`](docs/reliability.md), [`docs/chaos_cost_controls.md`](docs/chaos_cost_controls.md), [`docs/architecture/serving_resilience.md`](docs/architecture/serving_resilience.md).

---

## 🚢 Deployment & infrastructure

- Container images built from [`Dockerfile`](Dockerfile) with compose orchestration in [`docker-compose.yml`](docker-compose.yml).
- Kubernetes manifests, Kustomize overlays, and Prometheus rules live in [`deploy/`](deploy).
- Infrastructure-as-code blueprints are under [`infra/terraform`](infra/terraform) and reference deployment runbooks in [`DEPLOYMENT.md`](DEPLOYMENT.md).
- Release and cutover checklists reside in [`reports/prod_cutover_readiness_checklist.md`](reports/prod_cutover_readiness_checklist.md) and [`UPGRADE_SUMMARY.md`](UPGRADE_SUMMARY.md).

---

## 📖 Documentation guide

Start with [`docs/index.md`](docs/index.md) for a curated navigation of architecture guides, operational handbooks, quality gates, and training programmes. Key entry points include:

- Architecture & design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/architecture/system_overview.md`](docs/architecture/system_overview.md).
- Strategy & agent lifecycle: [`docs/agent.md`](docs/agent.md), [`docs/FPM-A.md`](docs/FPM-A.md).
- Governance & compliance: [`docs/governance.md`](docs/governance.md), [`DOCUMENTATION_SUMMARY.md`](DOCUMENTATION_SUMMARY.md).
- Roadmap & enablement: [`docs/roadmap.md`](docs/roadmap.md), [`docs/training_enablement_program.md`](docs/training_enablement_program.md).

Additional stakeholder assets are catalogued in [`stakeholders/README.md`](stakeholders/README.md).

---

## 🤝 Contributing & governance

- Follow the contribution guidelines in [`CONTRIBUTING.md`](CONTRIBUTING.md) and the community expectations in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- Security policies, disclosure processes, and secret handling live in [`SECURITY.md`](SECURITY.md) and [`docs/runbook_secret_rotation.md`](docs/runbook_secret_rotation.md).
- Documentation standards and governance workflows are described in [`documentation_governance.md`](docs/documentation_governance.md) and [`documentation_standardisation_playbook.md`](docs/documentation_standardisation_playbook.md).
- For release preparation, consult [`DOCUMENTATION_SUMMARY.md`](DOCUMENTATION_SUMMARY.md), [`TESTING_SUMMARY.md`](TESTING_SUMMARY.md), and [`SCRIPT_IMPROVEMENTS.md`](SCRIPT_IMPROVEMENTS.md).

---

## 📡 Community & support

- File issues and feature requests through GitHub Issues.
- Use the stakeholder directory in [`stakeholders/`](stakeholders) for communication cadences, RACI assignments, and escalation paths.
- Review [`newsfragments/`](newsfragments) entries and [`CHANGELOG.md`](CHANGELOG.md) for historical context.

---

## 📄 License

TradePulse is released under the [MIT License](LICENSE).

---

## 🇺🇦 Швидка довідка українською

- **Початок роботи:** пройдіть [швидкий старт](docs/quickstart.md), встановіть залежності з `requirements.lock` та виконайте `python -m interfaces.cli analyze --csv sample.csv --price-col close` для першої перевірки.
- **Дослідження та індикатори:** дивіться [`core/indicators`](core/indicators) та методичні матеріали в [`docs/indicators.md`](docs/indicators.md).
- **Бектести:** запускайте `python -m interfaces.cli backtest --csv sample.csv --window 200 --price-col close --fee 0.0005` або використовуйте конфігурації з [`configs/default.yaml`](configs/default.yaml).
- **Інфраструктура та запуск:** шаблони Kubernetes у [`deploy/`](deploy), Terraform — у [`infra/terraform`](infra/terraform), Docker-композиції — в [`docker-compose.yml`](docker-compose.yml).
- **Спостереження та операційні процедури:** основні інструкції в [`docs/monitoring.md`](docs/monitoring.md) та [`docs/operational_handbook.md`](docs/operational_handbook.md).
- **Команда та контакти:** структура відповідальностей у [`stakeholders/`](stakeholders) та вимоги до документації в [`docs/documentation_governance.md`](docs/documentation_governance.md).

