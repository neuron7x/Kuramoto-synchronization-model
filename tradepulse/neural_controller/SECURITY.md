# Risk Governance & Alignment

- **Mode Safety**: `mode=RED` disables `increase_risk`; AMBER requires both positive RPE and sufficient contingency energy `E`.
- **Tail Protection**: CVaR gate clamps allocations so ES(α) never breaches `cvar_limit`.
- **State Hygiene**: EKF is side-effect free; all state variables (`H, M, E, S`) stay within `[0, 1]`.
- **Auditability**: Controller returns a full decision snapshot including allocations, scale, belief, RPE, and sync status.
- **Config Governance**: Tunables live in YAML; edits are trackable via standard code review.
- **Thread Safety**: No global mutable singletons; instantiate per strategy/session.
