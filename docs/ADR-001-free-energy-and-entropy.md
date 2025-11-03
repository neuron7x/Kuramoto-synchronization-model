# ADR-001: Free Energy Functional and Entropy Thresholds

## Status
Accepted

## Context
The Thermodynamic Autonomic Control Layer (TACL) uses:
- Free energy F as a composite inefficiency proxy (latency, coherency degradation, resource usage).
- Entropy H of bond-type distribution as a proxy for topological disorder.

The current documentation referenced entropy thresholds that exceeded the theoretical bounds of the normalized Shannon entropy.

## Decision
We standardize the entropy definition and thresholds.

### Entropy Definition
Let `p_i` be the proportion of edges with bond type i, and `n` the number of distinct bond types present. Normalized Shannon entropy:

```
H_norm = -Σ_i p_i log(p_i) / log(n),    with H_norm ∈ [0, 1]
```

### Operational Thresholds (Normalized)
- Normal: H_norm < 0.7
- Elevated: 0.7 ≤ H_norm < 0.9
- Crisis: H_norm ≥ 0.9

These thresholds align with the bounded range of `H_norm` and can be tuned per environment.

### Free Energy
Document `F` as a weighted sum of normalized metrics:

```
F = w_lat * L + w_coh * (1 - C) + w_res * R
```

- L: mean latency_norm across active edges
- C: mean coherency across active edges
- R: normalized resource pressure (e.g., CPU/IO composite)
- Weights {w_lat, w_coh, w_res} are environment-tuned, sum to 1.0

We keep the monotonic constraint: accept mutations only if:

```
F_new ≤ F_old + ε
```

where `ε` is an adaptive tolerance derived from baseline EMA (documented in code and README).

## Consequences
- Update ML_CRISIS_PREDICTOR.md to use the normalized thresholds above.
- Add tests to ensure H_norm ∈ [0, 1] under random topologies (future work).
- Expose `H_norm` in `/thermo/status` to aid observability.
