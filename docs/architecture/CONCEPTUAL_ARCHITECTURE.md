# GeoSync Conceptual Architecture

> **Note**: The full detailed conceptual architecture documentation is available in Ukrainian at
> [CONCEPTUAL_ARCHITECTURE_UA.md](../CONCEPTUAL_ARCHITECTURE_UA.md). This document provides an
> English overview and navigation guide.

## Overview

This document series visualizes the conceptual elements of the GeoSync system and their
relationships through comprehensive diagrams. It serves as a high-level abstraction guide to
understanding the architecture.

## Available Visualizations

### 1. System Conceptual Map
**Diagram**: [`conceptual_map.mmd`](assets/conceptual_map.mmd)

High-level visualization showing all conceptual elements of the system including:
- 🌐 External Sources (Market data, Alternative data, News, Broker events)
- 📥 Integration Layer (Ingestion, Validation, Event Bus)
- 🧠 Processing Core
  - 📊 Indicators (Kuramoto, Ricci Flow, Entropy, Technical)
  - 🎯 Strategies (FETE DSL, Backtesting, Optimization)
  - 🧬 Neuromodulation (Dopamine, Serotonin, GABA)
  - ⚡ TACL (Thermodynamic control)
- 💼 Execution (Risk checks, Execution gateway, Broker adapters)
- 📡 Observability (Telemetry, Alerts, Audit)
- 👤 Interfaces (Web UI, CLI, API)

### 2. Neuromodulation System
**Diagram**: [`neuromodulation_system.mmd`](assets/neuromodulation_system.mmd)

Detailed visualization of neuromodulation control mechanisms:
- 💊 **Dopamine Subsystem**: Reward signal, prediction error, learning
- 🎯 **Serotonin Subsystem**: Risk assessment, system mood, strategy adaptation
- 🛑 **GABA Subsystem**: Activity monitoring, inhibition signal, cooldown period
- ⚙️ **Integration Center**: Signal integration, weighted coefficients, final modulation

**Inputs**: P&L history, Market conditions, Performance metrics, Trade frequency  
**Outputs**: Position size, Risk tolerance, Entry threshold, Exit speed

### 3. TACL - Thermodynamic Autonomic Control Layer
**Diagram**: [`tacl_system.mmd`](assets/tacl_system.mmd)

Visualization of the thermodynamic autonomic control system:
- 📊 **Metrics Collection**: Latency (P95/P99), CPU, Memory, Queue depth, Coherency drift, Packet loss
- 🧮 **Energy Calculation**: Free energy F = U - T·S (Helmholtz)
- 🎚️ **Threshold Validation**: F ≤ 1.35 safety boundary
- 🚨 **Crisis Management**: Detection, classification, protocol selection, recovery
- ⚙️ **Control Actions**: Proceed, throttle, rollback, alert

### 4. Signal Lifecycle
**Diagram**: [`signal_lifecycle.mmd`](assets/signal_lifecycle.mmd)

Sequence diagram showing the complete cycle from signal generation to execution:
1. Market data reception
2. Data validation and normalization
3. Feature store processing
4. Parallel indicator calculation (Kuramoto, Ricci, Entropy)
5. Strategy signal generation
6. Neuromodulation parameter adjustment
7. TACL thermodynamic validation
8. Risk management checks
9. Execution gateway routing
10. Broker confirmation
11. P&L update and learning feedback

### 5. Module Relationships
**Diagram**: [`module_relationships.mmd`](assets/module_relationships.mmd)

Detailed visualization of dependencies between system layers:
- **Data Layer**: Sources → Quality → Feature Store
- **Analytics Layer**: Indicators → Feature Engineering → Signal Generation
- **Decision Layer**: Strategy Engine → Risk Management → Portfolio Manager
- **Execution Layer**: Execution Engine → Order Management → Broker Adapters
- **Control Layer**: Neuromodulators, TACL Controller, Governance
- **Observability Layer**: Telemetry, Logging, Tracing

## Key Architectural Concepts

### Core Processing Components

**Indicators**:
- Kuramoto Oscillators — synchronization-based market analysis
- Ricci Flow — geometric curvature detection
- Entropy Measures — information-theoretic signals
- Technical Indicators — classic and modern coverage

**Strategies**:
- FETE DSL — declarative strategy definition
- Backtesting — event-driven simulation
- Optimization — genetic algorithms and Optuna framework

**Neuromodulation**:
- Dopamine — reward response and reinforcement learning
- Serotonin — risk regulation and mood control
- GABA — signal inhibition and overtrading prevention

**TACL**:
- Thermodynamic validation of system energy
- Free energy budget enforcement
- Crisis detection and automatic rollback

### Data Flow (8 Phases)

1. **Reception**: Raw data acquisition, normalization, validation, timestamping
2. **Enrichment**: Feature extraction, indicator calculation, hierarchical features, caching
3. **Signal Generation**: Kuramoto, Ricci, Entropy signals → Composite signal
4. **Neuromodulation**: Dopamine, Serotonin, GABA modulation → Parameter adjustment
5. **Strategic Decisions**: Strategy evaluation, position sizing, risk checks, order generation
6. **Thermodynamic Control**: Energy validation, crisis detection, circuit breaker
7. **Execution**: Pre-trade checks, routing, broker submission, confirmation
8. **Feedback**: Results recording, P&L update, model learning, telemetry

## TACL Metrics

| Metric | Description | Threshold | Weight |
|--------|-------------|-----------|--------|
| `latency_p95` | 95th percentile latency (ms) | 85.0 | 1.6 |
| `latency_p99` | 99th percentile latency (ms) | 120.0 | 1.9 |
| `coherency_drift` | Shared state drift | 0.08 | 1.2 |
| `cpu_burn` | CPU utilization ratio | 0.75 | 0.9 |
| `mem_cost` | Memory footprint (GiB) | 6.5 | 0.8 |
| `queue_depth` | Queue length | 32.0 | 0.7 |
| `packet_loss` | Packet loss ratio | 0.005 | 1.4 |

**Acceptable Energy Range**: F ≤ 1.35 (12% safety margin)

**Energy Formula**: F = U - T·S
- U = Internal energy (weighted penalties)
- T = Control temperature (0.60 constant)
- S = Stability entropy (headroom)

## Generating Diagrams

To generate SVG files from Mermaid sources:

```bash
./scripts/generate_conceptual_diagrams.sh
```

This requires:
- Node.js >= 18
- @mermaid-js/mermaid-cli (installed automatically)

## Viewing Diagrams

### In GitHub
GitHub automatically renders Mermaid diagrams in Markdown files.

### Locally

**Option 1: VS Code**
- Install "Markdown Preview Mermaid Support" extension
- Open file and use preview (Ctrl+Shift+V)

**Option 2: MkDocs**
```bash
mkdocs serve
```
Then open http://localhost:8000

**Option 3: Online**
- [Mermaid Live Editor](https://mermaid.live/)
- Copy `.mmd` file content into editor

## Related Documentation

- [Architecture Blueprint](../ARCHITECTURE.md) — Full system topology
- [System Overview](system_overview.md) — Component interactions
- [TACL Documentation](../TACL.md) — Thermodynamic control layer
- [Feature Store](feature_store.md) — Feature store architecture
- [Diagram Catalog](assets/README.md) — Complete diagram list

## Contributing

When updating diagrams:
1. Edit the corresponding `.mmd` file
2. Run generation script to update SVG
3. Commit both files (`.mmd` and `.svg`)
4. Update documentation references if needed

---

**Version**: 1.0.0  
**Last Updated**: 2025-11-17  
**Authors**: GeoSync Architecture Team
