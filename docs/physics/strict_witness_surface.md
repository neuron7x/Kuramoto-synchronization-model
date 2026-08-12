# Strict Witness Surface Ledger

Date: 2026-05-29

This file records strict physics witness files that are enforced by `.github/workflows/physics-kernel-gate.yml` but are not necessarily reflected in `docs/physics/evidence_matrix.md`, because that matrix is generated only from metadata declared in `.claude/physics/INVARIANTS.yaml`.

## Strict witness files

| File | Witnessed invariants | Surface |
|---|---|---|
| `tests/unit/physics/test_T9_kuramoto_transitions.py` | INV-K2, INV-K3 | Kuramoto subcritical and supercritical asymptotics |
| `tests/unit/physics/test_T10_ricci_bounds.py` | INV-RC1, INV-RC3 | Ollivier-Ricci universal and price-graph bounds |
| `tests/unit/physics/test_T11_dopamine_algebraic.py` | INV-DA1, INV-DA7 | TD-error sign and reward linearity |
| `tests/unit/physics/test_T12_serotonin_stability.py` | INV-5HT1, INV-5HT4, INV-5HT6 | Serotonin Lyapunov, sensitivity, tonic bounds |
| `tests/unit/physics/test_T13_free_energy_components.py` | INV-FE2 | Free-energy component non-negativity |
| `tests/unit/physics/test_T14_portfolio_energy_conservation.py` | INV-OMS1 | Portfolio kinetic-energy non-negativity |
| `tests/unit/physics/test_T15_oms_idempotency_causality.py` | INV-OMS2, INV-OMS3 | OMS idempotency and lifecycle causality |
| `tests/unit/physics/test_T16_signalbus_dag.py` | INV-SB1 | SignalBus acyclic fanout |

## Governance rule

If this ledger and `docs/physics/evidence_matrix.md` disagree, the disagreement is metadata drift, not automatic scientific failure. The closure path is to add exact `tests:` metadata to the invariant registry and regenerate the matrix.

## Do not promote

This ledger does not promote OOS, live-market, alpha, or criticality claims. It only records strict local witnesses.
