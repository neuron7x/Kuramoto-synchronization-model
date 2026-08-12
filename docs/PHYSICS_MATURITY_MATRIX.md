# GeoSync Physics Maturity Matrix

> **Status:** canonical. Machine-checked by
> `scripts/ci/check_physics_docs_canon.py`. The per-id law and invariant
> membership of each domain is authoritative in `docs/PHYSICS_CANON.manifest.json`;
> this matrix is the human-readable status view. No domain may imply a maturity
> above its evidence tier.

Maturity vocabulary (closed set): `FORMAL_LAW`, `INVARIANT`,
`DERIVED_COMPUTATIONAL_PROPERTY`, `HYPOTHESIS`, `NON_CLAIM_ANALOGY`.

| Domain | Maturity | Laws / Inv. | Code | Tests | Allowed claim | Forbidden claim | Verify | Open blocker |
|---|---|---|---|---|---|---|---|---|
| `graph_geometry` | `FORMAL_LAW` | 5 / 5 | `core/physics/forman_ricci.py`, `core/kuramoto/kuramoto_ricci_engine.py` | `tests/unit/physics/test_T1_*`, `test_KR4_*` | Discrete graph-curvature theorems hold within stated validity | Not a claim that market structure is governed by curvature | `pytest -q tests/unit/physics -k 'ricci or curvature'` | — |
| `nonlinear_synchronization` | `FORMAL_LAW` | 5 / 26 | `core/kuramoto/*`, `core/physics/lyapunov_*.py` | `tests/unit/physics/test_T2_*`, `test_T22_*`, `test_T23_*` | Kuramoto / Ott-Antonsen / Lyapunov results hold for the stated model | Not a claim that asset returns synchronize as a market law | `pytest -q tests/unit/physics -k 'kuramoto or lyapunov'` | — |
| `computational_physics_contract` | `DERIVED_COMPUTATIONAL_PROPERTY` | 4 / 11 | `core/physics/stochastic_thermodynamics.py`, `determinism_kit.py`, `uncertainty.py` | `tests/unit/physics/test_T6_*`, `test_T8_*`, `test_uncertainty.py` | Derived properties of the implementation, not empirical market facts | Not a claim that markets obey these identities | `pytest -q tests/unit/physics -k 'thermo or determinism or uncertainty'` | — |
| `market_microstructure_hypothesis` | `HYPOTHESIS` | 9 / 7 | `core/dro_ara/engine.py`, `coherence_bridge/*`, manifold contracts | `tests/unit -k 'dro_ara or manifold or coherence'` | Falsifiable research hypotheses; promotion needs real-data evidence | No out-of-sample edge, profitability, or rank asserted | `pytest -q tests/unit -k 'dro_ara or manifold or coherence'` | Multi-session real-data evidence absent |
| `neuro_symbolic_analogy` | `NON_CLAIM_ANALOGY` | 6 / 29 | `core/neuro/*`, `geosync/neuroeconomics/*` | `tests/unit -k 'serotonin or dopamine or gaba or cryptobiosis'` | Engineering risk-instrumentation analogies; labels are arithmetic proxies | Not a biological claim and not a market-physics law | `pytest -q tests/unit -k 'serotonin or dopamine or gaba'` | N/A (non-claim) |
| `execution_infrastructure` | `INVARIANT` | 10 / 22 | `core/indicators/trading.py`, OMS, SignalBus, HPC kernels | `tests/unit -k 'kelly or oms or signalbus or hpc'` | Machine-checkable contracts of the computation | Not a claim of profitability or live-venue readiness | `pytest -q tests/unit -k 'kelly or oms or signalbus or hpc'` | N/A |
| `personal_research_ontology` | `NON_CLAIM_ANALOGY` | 3 / 12 | `core/neuro/gradient_vital_signs.py`, PNCC kernel | `tests/integration/test_neurostack_integration.py`, PNCC tests | Author's research framing, scoped to the system's substrate | Not physics of markets and not an empirical claim | `pytest -q tests/unit -k 'gradient or pncc'` | N/A (non-claim) |

**Reading rule:** "Laws / Inv." counts and the exact ids are taken from the
manifest; if this table and the manifest disagree, the manifest wins and the
gate fails closed. Artifacts for `HYPOTHESIS` domains are evidence capsules
under `results/` / `artifacts/` and are not promotion-bearing until they pass
schema + null + falsifier with real data.
