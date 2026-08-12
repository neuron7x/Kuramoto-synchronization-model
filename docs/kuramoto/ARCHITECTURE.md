# NetworkKuramotoEngine — Architecture

The NetworkKuramotoEngine is the inverse-problem side of GeoSync's
Kuramoto stack. It consumes a matrix of log-returns (or any band-
limited multichannel signal), identifies the parameters of a
Sakaguchi–Kuramoto network

```
θ̇_i(t) = ω_i + Σ_j K_ij sin(θ_j(t − τ_ij) − θ_i(t) − α_ij) + ξ_i(t)
```

and exposes both a full :class:`NetworkState` for downstream
simulation / falsification and a streaming feature adapter for the
trading pipeline.

## Module layout

```
core/kuramoto/
├── contracts.py           # 7 frozen dataclasses, deep immutability
├── phase_extractor.py     # M1.2 — θ_i(t) from real signals
├── natural_frequency.py   # M1.4 — ω_i robust estimator
├── coupling_estimator.py  # M1.3 — sparse signed K_ij (MCP/SCAD/Lasso)
├── delay_estimator.py     # M2.1 — τ_ij joint per-row coord descent
├── frustration.py         # M2.2 — α_ij profile likelihood
├── synthetic.py           # M3.1 — SDDE ground-truth generator
├── metrics.py             # M2.4 — R, clusters, chimera, CSD, entropy
├── dynamic_graph.py       # M2.3 — sliding-window K(t)
├── falsification.py       # M3.2 — IAAFT, shuffle, rewire, counterfactuals
├── causal_validation.py   # M1.5 — Granger / optional PCMCI
├── oos_validation.py      # M3.3 — walk-forward + DM + Hansen SPA
├── network_engine.py      # orchestrator
└── feature.py             # M3.4 — two-tier trading adapter
```

Every module is a single-file unit with a ``frozen=True`` config
dataclass, a stateless primitive API, and a small class wrapper
that takes the config and exposes a verb-style method (``.estimate``,
``.extract``, ``.identify``, ``.update``). The modules compose only
through the contract types in ``contracts.py``.

## Data flow

```
raw returns (T, N)
       │
       ▼
  PhaseExtractor ──────────► PhaseMatrix
                                 │
                                 ├──► estimate_natural_frequencies ─► ω
                                 │
                                 ▼
                         CouplingEstimator ──► CouplingMatrix
                                 │
                                 ▼
                         DelayEstimator ──► DelayMatrix
                                 │
                                 ▼
                       FrustrationEstimator ──► FrustrationMatrix
                                 │
                                 ▼
                     NetworkState  ◄── noise_std (residual RMS)
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
             compute_metrics   OOS validation  NetworkKuramotoFeature
                    │                              (trading pipeline)
                    ▼
            EmergentMetrics
```

The orchestrator lives in :mod:`core.kuramoto.network_engine`; it
wires the stages in the order above and returns a
:class:`NetworkEngineReport` (state + metrics). The trading feature
adapter caches the state between periodic batch recalibrations and
computes per-bar features on the hot path in **< 1 ms** for N ≤ 50.

## Immutability and thread safety

- Every dataclass is ``@dataclass(frozen=True, slots=True)``.
- All ``np.ndarray`` fields pass through ``_FrozenArrayMixin``,
  which takes a defensive copy and clears ``flags.writeable``.
- ``frozen=True`` blocks field reassignment; the combination
  with the write-protected arrays makes the state deeply
  immutable.
- The trading feature's Tier 2 (batch) path writes a new
  :class:`NetworkState` as a single reference assignment; the
  Tier 1 (online) reader is therefore safe without locks.

## Reproducibility

- Every randomness source is an explicit
  ``numpy.random.Generator`` seeded from the config.
- The orchestrator is deterministic: given the same input
  phases and config, ``.identify`` returns equal arrays on
  every run.
- The synthetic generator (:mod:`core.kuramoto.synthetic`) is
  the authoritative fixture for all level-B / level-E tests.

## Dependencies

Core path: only ``numpy``, ``scipy``. Optional backends:

- ``PyEMD`` — CEEMDAN phase extraction
- ``ssqueezepy`` — synchrosqueezed CWT phase extraction
- ``tigramite`` — PCMCI causal validation

The core estimators do **not** depend on ``skglm``,
``stability-selection`` (the PyPI package is broken since
sklearn ≥ 1.3), ``leidenalg``, ``ewstools``, ``antropy``, or
``nolitsa``. Every algorithm that would normally come from
one of those packages has a pure-numpy implementation in this
module tree.
