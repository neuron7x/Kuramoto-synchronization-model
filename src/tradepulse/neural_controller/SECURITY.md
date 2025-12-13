# Risk Governance & TACL Alignment

- **MFED Compliance**: The neural controller is the governing brain enforcing Monotonic Free Energy Descent. RED state hard-disables
  `increase_risk`; AMBER allows it only when `E > tau_E_amber` *and* RPE is positive.
- **Tail Protection**: CVaR gate scales allocations so ES(α) never breaches `cvar_limit`; realised tail ES95 is exported for monitoring.
- **State Hygiene**: EKF is side-effect free; all latent variables (`H, M, E, S`) remain within `[0, 1]` with a single update per tick.
- **Auditability**: Structured JSON logs capture `{mode, RPE, belief, allocs, alloc_scale, sync_order, MFED blocks}`.
- **Config Governance**: All knobs (including sync thresholds and TACL generations) live in YAML and are covered by tests.
- **Thread Safety**: No global mutable singletons; instantiate per strategy/session.
