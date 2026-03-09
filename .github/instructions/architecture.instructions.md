# Architecture instructions
- Keep module boundaries explicit and avoid cross-layer coupling.
- Respect dependency direction: outer layers depend on inner interfaces, not inverse.
- Isolate side effects and keep pure core logic deterministic.
- Prefer narrow interfaces for execution/risk/security boundaries.
