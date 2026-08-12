Follow-up to #1107. This issue tracks building the full `SecondOrderStabilityAudit`:

- [ ] `energy_like_drift` — swing-energy drift bound (cf. INV-K8/K9)
- [ ] `phase_spread_bound` — bounded phase-spread / no unphysical divergence
- [ ] `solver_metadata` — record solver, method, dt policy, rtol/atol
- [ ] `stiffness_assumption` — detect/declare stiffness regime
- [ ] `cross_solver_reference` — agreement vs an independent integrator

**Non-waivable:** until these land, the engine guard is partial; passing CI does
not constitute a complete numerical stability validation.
