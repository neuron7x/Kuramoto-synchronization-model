# GeoSync Unified Div/Conv Protocol

This document captures the initial public specification for the GeoSync
protocol described in the milestone brief.  The artefacts introduced in this
iteration focus on the Div/Conv geometry while keeping the interfaces stable
for future integration with causal reasoning, risk-aware reinforcement
learning, online regime detection, multimodal fusion, HPC and governance
layers.

## Scope of this drop

1. **Formal Div/Conv geometry** – `src/geosync/protocol/divconv.py`
   ships reference implementations for the key observables:
   - price and flow gradients (`∇P_t`, `∇F_t`) with explicit time-warp
     invariance;
   - angular metrics (`θ_t`, `κ_t`);
   - a divergence functional with user-supplied metrics;
   - quantile-based divergence and convergence thresholds (`τ_d`, `τ_c`);
   - a canonical portfolio aggregation rule for multi-asset signals.
2. **Machine-verifiable contracts** – `tests/protocol/test_divconv.py`
   provides property-based regression tests that guard scaling invariance,
   positive semi-definiteness of the induced metric, and aggregation
   semantics.
3. **API surface** – `src/geosync/protocol/__init__.py` curates the public
   entrypoints that downstream services can depend on.  The interfaces favour
   deterministic numerics and explicit validation so they can be safely
   embedded into risk, causal and control pipelines.

## Roadmap alignment

* The `DivConvSnapshot` and `DivConvSignal` dataclasses provide the hooks for
  attaching causal attributions, risk limits and governance metadata without
  altering the mathematical core.
* Quantile-based `τ_d`/`τ_c` thresholds and the metric factory give the
  regime-detection stack a principled starting point that is amenable to
  Bayesian optimisation and adaptive windowing.
* The aggregation primitive normalises risk weights by default, which keeps
  the protocol compatible with risk-aware control policies and ensures that
  exposure accounting is auditable.
* All observables are deterministic functions of numpy arrays, simplifying
  deterministic replay in HPC environments and easing the creation of
  containerised reference scenarios.

Future drops will extend these interfaces with causal SCM integration, robust
control hooks, online calibration loops, multimodal fusion adaptors and full
observability contracts while preserving backward compatibility.
