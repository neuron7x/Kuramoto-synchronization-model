# FILES INSPECTED — Kuramoto–Ricci pilot

Read / analysed (no edit unless noted):

- `core/kuramoto/__init__.py` — public API surface *(edited: export CouplingSpec)*
- `core/kuramoto/config.py` — KuramotoConfig, coupling docstring *(edited: from_coupling_spec)*
- `core/kuramoto/engine.py` — `_resolve_adjacency`, `_dtheta_dt` (coupling assembly)
- `core/kuramoto/contracts.py` — CouplingMatrix + frozen-dataclass primitives (reused `_require`, `_check_square`, `_check_finite`)
- `core/kuramoto/kuramoto_ricci_engine.py` — JAX RHS `Σ A·sin(δ)` (confirmed single-scale path)
- `core/kuramoto/phase_extractor.py` — Hilbert/CEEMDAN/SSQ-CWT + Q1–Q4 gates (already principled; no std/mean proxy)
- `core/kuramoto/network_engine.py` — orchestrator (regression target)
- `core/indicators/kuramoto.py` — arctan2 is analytic-signal Hilbert phase, not a proxy
- `core/cross_asset_kuramoto/{engine,invariants,signal,types}.py` — surveyed
- `CLAUDE.md` — invariant registry (INV-K1..K10, INV-RC1..3, INV-KR1..3)

Created:

- `core/kuramoto/coupling_spec.py` — CouplingSpec contract
- `tests/unit/core/test_kuramoto_coupling_spec.py` — 20 regression tests
- `artifacts/lab_pilot/kuramoto_ricci/*` — evidence
