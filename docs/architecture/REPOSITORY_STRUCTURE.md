# TradePulse Repository Structure

**Last Updated:** 2025-12-08  
**Version:** 1.0.0  
**Status:** ✅ Active

This document provides a comprehensive overview of the TradePulse repository structure, explaining the purpose of each major directory and file organization principles.

## Table of Contents

- [Overview](#overview)
- [Root Directory Structure](#root-directory-structure)
- [Source Code Organization](#source-code-organization)
- [Configuration Management](#configuration-management)
- [Documentation Structure](#documentation-structure)
- [Testing Infrastructure](#testing-infrastructure)
- [Development Tools](#development-tools)
- [Package Structure](#package-structure)

---

## Overview

TradePulse follows a **flat package structure** where major components live at the root level. This design supports:

- **Direct imports**: `from core import ...`, `from execution import ...`
- **Component independence**: Each directory is a standalone package
- **Clear boundaries**: Separation between core logic, applications, and infrastructure
- **Backward compatibility**: Shim layers for legacy code paths

---

## Root Directory Structure

```
TradePulse/
├── analytics/              # Market analytics and signal generation
├── application/            # Application services (API, runtime, security)
├── apps/                   # User-facing applications (web dashboard, risk guardian)
├── backtest/               # Backtesting engine and strategies
├── cli/                    # Command-line tooling and developer UX entrypoints
├── core/                   # Core trading logic and neuromodulator systems
├── cortex_service/         # Cortex orchestration service surface for control-plane flows
├── execution/              # Order execution and exchange adapters
├── observability/          # Logging, metrics, tracing, health checks
├── runtime/                # Runtime controllers and lifecycle management
├── src/                    # Source package (SDK, protocol implementations)
│   ├── tradepulse/         # Main SDK package
│   └── tradepulse_agent/   # Agent framework
├── tests/                  # Test suite (unit, integration, e2e, property-based)
├── docs/                   # Documentation
├── examples/               # Usage examples and demos
├── scripts/                # Utility scripts
├── tools/                  # Development and deployment tools
├── ui/                     # Frontend experience layer (dashboard bundle and shared assets)
└── ...                     # Additional components
```

### Key Root Directories

#### Business Logic
- **`analytics/`** - Market regime detection, signal generation, statistical analysis
- **`core/`** - Core trading engine, neuromodulator systems, indicators, ML models
- **`execution/`** - Order execution, exchange adapters, risk management
- **`backtest/`** - Event-driven backtesting framework, simulation, strategies

#### Applications & Services
- **`application/`** - API services, configuration management, runtime services
- **`apps/`** - User-facing applications (web dashboard, risk guardian)
- **`cli/`** - Unified CLI surface for operators and developers
- **`ui/`** - Frontend delivery (dashboard bundle, design system assets)
- **`observability/`** - Logging, metrics, tracing, health monitoring

#### Infrastructure
- **`runtime/`** - Runtime controllers, thermodynamic system, lifecycle management
- **`infra/`** - Infrastructure as code (Terraform, Kubernetes configs)
- **`deploy/`** - Deployment scripts and configurations
- **`monitoring/`** - Monitoring dashboards (Grafana)

#### Development
- **`src/`** - Python source packages (`tradepulse`, `tradepulse_agent`)
- **`tests/`** - Comprehensive test suite
- **`tools/`** - Development tools (linting, testing, deployment utilities)
- **`scripts/`** - Utility scripts for common tasks

#### Special Purpose
- **`cortex_service/`** - Dedicated Cortex service entrypoint for control-plane orchestration
- **`nak_controller/`** - Neuromodulator controller (standalone module)
- **`neurotrade_pro/`** - Advanced trading models (legacy, being refactored)
- **`neuropro/`** - Professional neuromodulation features
- **`sandbox/`** - Isolated testing environment
- **`formal/`** - Formal verification proofs

---

## Source Code Organization

### Main Packages

#### `tradepulse/` (Root Shim)
Backward compatibility shim that forwards to `src.tradepulse`:
- `tradepulse/__init__.py` - Import forwarding logic
- `tradepulse/neural_controller/` - Neural controller module (direct)
- `tradepulse/analytics/` - Analytics utilities (direct)
- `tradepulse/risk/` - Risk management (direct)

#### `src/tradepulse/` (Main SDK)
The primary SDK package:
- `api/` - API clients and interfaces
- `connectors/` - Exchange connectors
- `core/` - Core SDK functionality
  - `neuro/` - Neuromodulator implementations (dopamine, serotonin, etc.)
- `data/` - Data management and validation
- `features/` - Feature engineering
- `indicators/` - Technical indicators
- `integration/` - Integration utilities
- `live/` - Live trading components
- `policy/` - Trading policies
- `portfolio/` - Portfolio management
- `protocol/` - Protocol implementations
- `regime/` - Market regime detection
- `risk/` - Risk management
- `sdk/` - SDK core modules
- `utils/` - Utility functions

#### `src/tradepulse_agent/`
Agent framework for autonomous trading:
- Agent lifecycle management
- Environment interaction
- Decision-making framework
- Memory and learning systems

### Core Modules

#### `core/` - Core Trading Logic
- `agent/` - Trading agent implementations
- `architecture/` - System architecture components
- `compliance/` - Regulatory compliance
- `config/` - Configuration management
- `data/` - Data pipeline and validation
- `engine/` - Trading engine core
- `events/` - Event system
- `experiments/` - Experiment tracking
- `features/` - Feature engineering
- `idempotency/` - Idempotent operations
- `indicators/` - Technical indicators
- `ml/` - Machine learning models
- `neuro/` - Neuromodulator systems
  - `adaptive_calibrator.py` - Auto-calibration
  - `amm.py` - Adaptive Market Mind
  - `ecs_regulator.py` - Endocannabinoid system
  - `fractal_regulator.py` - Fractal regulation
  - `motivation.py` - Motivation systems
- `orchestrator/` - Component orchestration
- `phase/` - Trading phase management
- `pipelines/` - Data pipelines
- `reporting/` - Report generation
- `security/` - Security controls
- `strategies/` - Trading strategies
- `utils/` - Utility functions
- `validation/` - Validation framework

#### `execution/` - Order Execution
- `adapters/` - Exchange adapters (Binance, Coinbase, etc.)
- `arbitrage/` - Arbitrage execution
- `hft/` - High-frequency trading
- `resilience/` - Resilience patterns (circuit breakers, retries)
- `risk/` - Execution risk management
- `canary.py` - Canary deployment controller
- `oms.py` - Order Management System

#### `analytics/` - Market Analytics
- `code_health/` - Code quality analytics
- `demos/` - Demo applications
- `fpma/` - Fractal Pattern Market Analysis
- `math_trading/` - Mathematical trading models
- `regime/` - Market regime detection
- `signals/` - Signal generation
- `staging/` - Staging analytics

---

## Configuration Management

TradePulse uses **three separate configuration directories** for different purposes:

### `conf/` - Hydra Framework Configuration
- **Purpose:** Hydra-based application configuration with composition and overrides
- **Contents:**
  - `config.yaml` - Main Hydra config
  - `desensitization/` - Data desensitization settings
  - `experiment/` - Experiment configurations (dev, staging, prod, ci)
  - `nak/` - NAK controller configs

### `config/` - Core System Configuration
- **Purpose:** Core neuromodulator and thermodynamic system settings
- **Contents:**
  - `default_config.yaml` - System defaults
  - `dopamine.yaml` - Dopamine neuromodulator
  - `thermo_config.yaml` - Thermodynamic control layer
  - `profiles/` - Configuration profiles (conservative, normal, aggressive)

### `configs/` - Application Configuration
- **Purpose:** Service-level and application-specific configurations
- **Contents:**
  - Strategy configs: `amm.yaml`, `fhmc.yaml`, etc.
  - Neuromodulator configs: `serotonin.yaml`, `gaba.yaml`, etc.
  - System configs: `markets.yaml`, `risk.yaml`, `performance_budgets.yaml`
  - Subdirectories: `api/`, `live/`, `security/`, `rbac/`, `tls/`, etc.

**See [Configuration Structure Guide](configuration_structure.md) for detailed documentation.**

---

## Documentation Structure

### `docs/` - Documentation Root

```
docs/
├── index.md                    # Documentation portal homepage
├── ARCHITECTURE.md             # System architecture overview
├── FORMALIZATION_INDEX.md      # Formalization master index
├── DOCUMENTATION_SUMMARY.md    # Documentation registry (moved to root)
│
├── requirements/               # Requirements specifications
│   ├── product_specification.md  # Product spec (moved from project.md)
│   └── requirements-specification.md
│
├── releases/                   # Release documentation
│   └── release-notes.md        # Release notes (moved from root)
│
├── architecture/               # Architecture documentation
│   ├── configuration_structure.md  # Config directory guide
│   ├── CONCEPTUAL_ARCHITECTURE.md
│   └── ...
│
├── adr/                        # Architecture Decision Records
│   ├── 0001-*.md              # Published ADRs
│   └── template.md            # ADR template
│
├── api/                        # API documentation
├── security/                   # Security documentation
├── testing/                    # Testing guides
├── templates/                  # Documentation templates
├── examples/                   # Usage examples
└── ...                         # Additional guides
```

### Root-Level Documentation

Key documentation files at repository root:
- `README.md` - Main entry point
- `CHANGELOG.md` - Version history
- `CONTRIBUTING.md` - Contribution guidelines
- `SETUP.md` - Installation guide
- `TESTING.md` - Testing framework
- `DEPLOYMENT.md` - Deployment procedures
- `SECURITY.md` - Security policy
- `DOCUMENTATION_SUMMARY.md` - Documentation registry
- `LICENSE` - License (TPLA)
- `PATENTS.md` - Patent policy
- `CODE_OF_CONDUCT.md` - Code of conduct
- `CODEOWNERS` - Code ownership

---

## Testing Infrastructure

### `tests/` - Test Suite

```
tests/
├── unit/                   # Unit tests
├── integration/            # Integration tests
├── e2e/                    # End-to-end tests
├── property/               # Property-based tests (Hypothesis)
├── performance/            # Performance benchmarks
├── security/               # Security tests
├── fuzz/                   # Fuzzing tests
├── smoke/                  # Smoke tests
├── nightly/                # Nightly regression tests
├── fixtures/               # Test fixtures
├── conftest.py            # Pytest configuration
└── ...                     # Additional test categories
```

### Test Organization Principles

1. **Unit tests**: One test file per source file (`test_<module>.py`)
2. **Integration tests**: Test component interactions
3. **Property tests**: Use Hypothesis for property-based testing
4. **Performance tests**: Benchmark critical paths
5. **Security tests**: Validate security controls

---

## Development Tools

### `tools/` - Development Utilities

- `architecture/` - Architecture analysis tools
- `compliance/` - Compliance checking
- `coverage/` - Code coverage tools
- `dependencies/` - Dependency management
- `docs/` - Documentation generation
- `mutation/` - Mutation testing
- `observability/` - Observability tools
- `release/` - Release automation
- `schema/` - Schema validation
- `security/` - Security scanning
- `testing/` - Testing utilities
- `vendor/` - Vendored dependencies

### `scripts/` - Utility Scripts

- `api_management/` - API management scripts
- `commands/` - CLI command implementations
- `data_annotation/` - Data annotation tools
- `deploy/` - Deployment scripts
- `localization/` - Localization utilities
- `mlops/` - MLOps automation
- `nightly/` - Nightly job scripts
- `performance/` - Performance tools
- `runtime/` - Runtime utilities
- `sanity_cleanup/` - Cleanup scripts
- `tests/` - Test utilities

---

## Package Structure

### Python Package Configuration

**File:** `pyproject.toml`

Key packages included in distribution:
- `analytics` - Analytics modules
- `application` - Application services
- `backtest` - Backtesting engine
- `core` - Core trading logic
- `domain` - Domain models
- `execution` - Execution engine
- `interfaces` - Interface definitions
- `libs` - Shared libraries
- `markets` - Market adapters
- `modules` - Reusable modules
- `observability` - Observability stack
- `src` - Source packages
- `tradepulse` - Main package shim
- `tradepulse_agent` - Agent framework
- `tools` - Development tools

### Package Data

- `py.typed` - Type information for all packages
- `tradepulse.neural_controller/config/*.yaml` - Neural controller configs

---

## Special Directories

### `artifacts/` - Generated Artifacts
Build and runtime artifacts (gitignored, has `.gitkeep`):
- `cns_stabilizer/` - CNS stabilizer event logs
- `configs/` - Generated configuration templates

### `backlog/` - Requirements Management
Project requirements and backlog:
- `requirements.json` - Structured requirements
- `requirements.csv` - Spreadsheet format
- `jira_import.csv` - Jira import format
- `report.md` - Requirements analysis report

### `reports/` - Generated Reports
Generated analysis reports (gitignored with exceptions):
- `performance/` - Performance reports
- `incidents/` - Incident reports
- `disaster-recovery/` - DR reports
- Various audit and security reports (committed with `git add -f`)

### `state/` - Runtime State
Runtime state storage (gitignored, has `.gitkeep`)

### `newsfragments/` - Release Notes
Towncrier fragments for changelog generation (has `.gitkeep`)

---

## File Organization Principles

### General Guidelines

1. **Flat is better than nested**: Keep major packages at root level
2. **Packages, not modules**: Every directory with Python code has `__init__.py`
3. **Clear boundaries**: Each top-level directory is independent
4. **Intentional structure**: Config directories serve different purposes
5. **Documentation co-location**: Keep docs close to code when appropriate

### Naming Conventions

- **Directories**: lowercase with underscores (`my_module/`)
- **Python files**: lowercase with underscores (`my_file.py`)
- **Configuration**: lowercase with underscores (`my_config.yaml`)
- **Documentation**: UPPERCASE for important docs (`README.md`, `ARCHITECTURE.md`)
- **Tests**: prefix with `test_` (`test_my_module.py`)

### What Goes Where

| Type | Location | Example |
|------|----------|---------|
| Core logic | `core/`, `execution/`, `backtest/` | Trading engine |
| Applications | `apps/`, `application/` | Web dashboard |
| Utilities | `tools/`, `scripts/` | Deployment scripts |
| Tests | `tests/` | All test files |
| Docs | `docs/` | Architecture docs |
| Config | `conf/`, `config/`, `configs/` | YAML configs |
| Generated | `artifacts/`, `reports/` | Build artifacts |

---

## Migration History

### 2025-12-08: Repository Organization

**Changes:**
1. Removed obsolete `README_OLD_BACKUP.md`
2. Moved `project.md` → `docs/requirements/product_specification.md`
3. Moved `release-notes.md` → `docs/releases/release-notes.md`
4. Created `docs/architecture/configuration_structure.md`
5. Added `tradepulse` package to `pyproject.toml` includes
6. Updated all references to moved files
7. Added missing `__init__.py` files:
   - `execution/resilience/__init__.py`
   - `analytics/demos/__init__.py`

**Rationale:**
- Improve discoverability of documentation
- Centralize requirements in `docs/requirements/`
- Document intentional separation of config directories
- Fix package distribution to include shim layer

---

## Related Documentation

- [Configuration Structure Guide](configuration_structure.md) - Detailed config directory documentation
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture overview
- [DOCUMENTATION_SUMMARY.md](../../DOCUMENTATION_SUMMARY.md) - Documentation registry
- [CONTRIBUTING.md](../../CONTRIBUTING.md) - Contribution guidelines

---

**Maintained by:** Platform Architecture Team  
**Review Cadence:** Quarterly  
**Last Reviewed:** 2025-12-08
