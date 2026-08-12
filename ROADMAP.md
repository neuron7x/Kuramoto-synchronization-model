---
doc_status:
  status: aspirational
  authoritative_for:
    - strategic_roadmap
  valid_from: 2026-07-19
---

# Roadmap

> This document tracks the strategic direction of GeoSync. Tactical issues
> and bug fixes live in the [issue tracker](https://github.com/neuron7xLab/GeoSync/issues).
> For a deep dive on the architectural invariants, see
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Principles

Every item below must respect the three non-negotiable invariants of the
project:

1. **Determinism.** Every signal, backtest, and execution decision must be
   reproducible bit-for-bit given the same inputs and seed.
2. **Traceability.** Every decision must carry a full provenance trail that
   satisfies MiFID II / SEC Rule 15c3-5 audit requirements.
3. **Scientific rigour.** No heuristics without a peer-reviewed reference.
   Every indicator ships with its mathematical statement and the paper it
   came from.

---

## Current Release — v1.1.0 (April 2026)

| Area | Status |
|---|---|
| CI hardening (fail-closed gates, SAST split, supply-chain) | ✅ shipped |
| Test coverage boost (+771 tests, 9,759 total) | ✅ shipped |
| Community polish (CITATION.cff, YAML issue forms, CODEOWNERS) | ✅ shipped |
| Branch protection ruleset for `main` | ✅ enforced |

## Near-term — v1.2.0

**Theme: performance and production hardening.**

- [ ] Complete `execution/live_loop` integration test harness with mock
      venues for sub-millisecond latency assertions.
- [ ] Cover `execution/oms` integration paths (state persistence, crash
      recovery, partial-fill reconciliation) — target 90%+ coverage.
- [ ] Complete `core/data/pipeline` end-to-end tests (`run()`
      orchestration with mocked drift/quality/backfill collaborators).
- [ ] Publish reproducible benchmark suite (Kuramoto engines, Ricci
      curvature, event-driven backtest) with hardware baselines in
      [`docs/benchmarks.md`](docs/benchmarks.md).
- [ ] Rust acceleration coverage for hot-path indicators (Kuramoto order
      parameter, Hilbert transform) via `rust/geosync-accel`.
- [ ] Overall coverage target: 89% for `core + backtest + execution`.

## Mid-term — v1.3.0

**Theme: research depth and exchange connectivity.**

- [ ] Multi-scale Kuramoto with hierarchical coupling across asset classes
      (equities / FX / commodities / crypto).
- [ ] Ollivier-Ricci flow on full graph (current implementation uses MST
      for tractability on very large graphs).
- [ ] Full Binance + Coinbase WebSocket order-book connectors with
      deterministic replay mode.
- [ ] Walk-forward backtester with purged k-fold and combinatorial
      cross-validation (Lopez de Prado methodology).
- [ ] OpenTelemetry tracing for every decision path (indicator →
      strategy → risk → execution).

## Long-term — v2.0.0

**Theme: autonomous research agent and live deployment.**

- [ ] Autonomous hypothesis generation and testing loop (neuro-symbolic
      agent proposing new signals, backtester validating them, RL-based
      capital allocation).
- [ ] Execution-realism harness (paper/replay) with formal verification
      of the kill-switch state machine — research instrumentation, not a
      live-trading product.
- [ ] Distributed Kuramoto simulation on multi-GPU / TPU clusters
      (already scaffolded via `JaxKuramotoEngine`).
- [ ] Ingestion of alternative data (satellite, on-chain, text) with
      modality-specific feature engineering pipelines.
- [ ] Full Bayesian portfolio optimisation with uncertainty propagation.

---

## Strategic Addendum

For CNS-aligned, witness-first architectural priorities derived from the project
owner's doctrine, see [`docs/CNS_ALIGNMENT_DEEP_TASKS.md`](docs/CNS_ALIGNMENT_DEEP_TASKS.md).

## How to Influence the Roadmap

1. Open a **feature request** issue using the structured YAML form.
   Lead with the problem, not the solution.
2. Link peer-reviewed references — the scientific rigour invariant applies
   to the roadmap too.
3. Architecture-level proposals should be drafted as
   [Architecture Decision Records](docs/adr/) against a concrete trade-off.

## Non-Goals

To keep the project focused, the following are **explicitly out of scope**:

- **Black-box deep learning as a primary signal source.** We may use deep
  models as components, but every signal must be interpretable down to a
  mathematical statement.
- **High-frequency market making.** GeoSync targets medium-frequency
  strategies (seconds to minutes), not colocation arbitrage.
- **Retail-facing trading UI.** The `apps/web` dashboard is for research
  operators; we will not ship a broker-style UI.
- **Proprietary exchange integrations behind private credentials in this
  repository.** Private venue adapters live in consumer repositories.
