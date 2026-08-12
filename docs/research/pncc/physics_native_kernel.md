# PNCC-F: Physics-Native Kernel (Composition Layer)

**Status:** experimental, opt-in. Defaults inert (`lambda_thermo = lambda_irreversibility = 0.0`).
**Module:** `tacl/physics_native_kernel.py`
**Tests:** `tests/tacl/test_physics_native_kernel.py` (15 functions, including 1000-draw INV-FREE-ENERGY falsification)
**Invariant:** INV-FREE-ENERGY (P0, universal)
**Hypothesis status:** HYP-5 (combined loop improves accuracy or preserves it under lower compute) — remains a 90-day hypothesis. This PR ships the controller, **not** the validation.

## Composition

```
PhysicsNativeKernel
   │
   ├── DRFreeEnergyModel (tacl/dr_free.py — already on main)
   │     └── F_robust  via box-ambiguity adversarial metrics
   │
   ├── ThermodynamicBudget (core/physics/thermodynamic_budget.py — PNCC-A, #378)
   │     └── total_proxy_cost  ← token + latency + entropy + irreversibility
   │
   └── ReversibleGate (core/physics/reversible_gate.py — PNCC-C, #380)
         └── audit_hash + rollback ledger
```

## Decision Rule

For each candidate action `c` over `(metrics, ambiguity, cfg)`:

```
composite(c) = F_robust(metrics, ambiguity)
             + lambda_thermo · total_proxy_cost(c)
             + lambda_irreversibility · irreversibility_score(c)
```

Selection:
- If `state == DORMANT` (per `robust_energy_state`) → return `chosen=None`, `state="DORMANT"`.
- If ≥2 candidates within `tie_tolerance` of `min(composite)` AND `fail_closed_on_tie=True` → return `chosen=None`, `state="DORMANT"`.
- Otherwise → `chosen = argmin(composite)`, gate through `ReversibleGate.gate(...)`, return `audit_hash` + full per-candidate `CompositeScore` trace.

## INV-FREE-ENERGY (P0, universal)

> For non-empty `candidates` and any `(metrics, ambiguity, cfg)`:
> - **(a)** `chosen is not None` ∧ `chosen.composite == min(composites)`, OR
> - **(b)** `chosen is None` ∧ `state == "DORMANT"` ∧ ≥2 candidates within `tie_tolerance` of `min(composites)`.
>
> **Falsification axis:** 1000 random `(candidates × metrics × ambiguity)` draws. Any decision where `chosen.composite > min(composites) + tie_tolerance` AND `state != "DORMANT"` is a violation.

Test pointer: `tests/tacl/test_physics_native_kernel.py::test_invariant_falsification_random_1000`.

## Public API

Dataclasses (frozen, slotted):
- `CandidateAction` — one action under evaluation
- `PhysicsNativeKernelConfig` — `lambda_thermo`, `lambda_irreversibility`, `tie_tolerance`, `fail_closed_on_tie`, `ambiguity_radii`
- `CompositeScore` — per-candidate audit row
- `KernelDecision` — full output: chosen, state, scores, audit_hash, decision_trace, robust_margin, reason

Functions / class:
- `evaluate_candidate(candidate, metrics, ambiguity, cfg, *, free_energy_model) -> CompositeScore`
- `select_action(candidates, metrics, ambiguity, cfg, *, free_energy_model) -> KernelDecision`
- `PhysicsNativeKernel(cfg=None, *, free_energy_model=None, gate=None).decide(candidates, metrics, ambiguity=None, timestamp_ns=0) -> KernelDecision`

## Composability Properties

- `lambda_thermo == 0 ∧ lambda_irreversibility == 0` ⇒ kernel reduces exactly to pure DR-FREE selection on `F_robust`. Confirmed by `test_lambda_thermo_zero_recovers_pure_dr_free` (algebraic, exact).
- Single candidate ⇒ chosen is that candidate AND `audit_hash` is set. `test_single_candidate_recovers_dr_free`.
- Empty candidates ⇒ DORMANT (fail-closed). `test_empty_candidates_returns_dormant`.

## Known Limitations

- Default weights `lambda_thermo = lambda_irreversibility = 0` mean kernel reduces to DR-FREE-only selection. The thermodynamic-budget penalty is **opt-in** by setting non-zero weights. There is no online learning of weights.
- No PNCC-D (CNS proxy) plug-in. `CNSProxyState` is not yet wired in main; the kernel does not constrain by operator state. When PNCC-D ships with a real telemetry pipeline, scheduling-constraint hooks land here as a follow-up.
- DRO ambiguity set is rectangular box only (matches `tacl/dr_free.py`). KL or Wasserstein balls not supported.
- Thermodynamic-budget components are dimensionless proxies, not joules. Calibration of `lambda_thermo` to real cost is per-deployment.

## No-Bio-Claim Disclaimer

This module composes proxy costs (Landauer-style information-erasure proxy + Bennett-style reversibility audit + DRO-robust free-energy minimization) into a single decision controller. It does NOT diagnose, treat, or modify any biological state, and it makes NO claim of cognitive improvement. HYP-5 (combined loop improves accuracy or preserves it under lower compute) is a 90-day hypothesis that requires a registered EvidenceClaim with baseline, intervention, control, n_samples, effect_size, and 95% confidence interval — see `tacl/evidence_ledger.py`.

## References

Verified foundational citations only (per the verify-before-forward contract from PR #382):

- **Landauer 1961** — *Irreversibility and Heat Generation in the Computing Process*, IBM J. Res. Dev. 5, 183. Source for INV-LANDAUER-PROXY.
- **Bennett 1973** — *Logical Reversibility of Computation*, IBM J. Res. Dev. 17, 525. Source for INV-REVERSIBLE-GATE.
- **Friston 2010** — *The free-energy principle: a unified brain theory?*, Nature Reviews Neuroscience 11, 127. Source for the F-minimization framing.
- **DRO theory** — Wiesemann/Kuhn/Sim 2014 (and follow-ups). Source for the box-ambiguity adversarial-metric formulation in `tacl/dr_free.py`.

No 2025/2026 citations.

## Registry

- Will be registered in `.claude/physics/INVARIANTS.yaml::pncc.free_energy` and `physics_contracts/catalog.yaml::pncc.free_energy_argmin` in a follow-up coordination PR (Wave 2.5), mirroring how INV-LANDAUER-PROXY / INV-REVERSIBLE-GATE / INV-NO-BIO-CLAIM landed via PR #383.
