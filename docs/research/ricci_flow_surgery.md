# Discrete Ricci flow + neckpinch surgery

**Status.** Experimental, opt-in. `KuramotoRicciFlowEngine` retains byte-identical default behavior unless `enable_discrete_flow=True` and/or `enable_neckpinch_surgery=True`.

## Implemented files
- `core/kuramoto/ricci_flow.py`
- `core/kuramoto/ricci_flow_engine.py` (additive integration only)
- `tests/unit/core/test_ricci_flow_surgery.py`

## Formula

Discrete Ricci flow (Hamilton 1982; Chow & Luo 2003; arXiv:2510.15942):

```
w_ij^{n+1} = max(0, w_ij^n − η · κ_ij · w_ij^n)
```

Optional total-edge-mass conservation rescales so `Σ w_ij` is preserved.

Neckpinch surgery candidates:
- `0 < w_ij ≤ eps_weight`, or
- `κ_ij ≤ −1 + eps_neck` (Ollivier singular tail).

Bridges (per `networkx.bridges`) are clamped to `eps_weight` rather than removed when `preserve_connectedness=True`. Removed-count is capped at `floor(max_surgery_fraction · n_active_edges)` per call.

## Inputs
- `weights`: `(N, N)` symmetric, non-negative, zero-diagonal float64.
- `curvature`: `dict[(i, j), κ_ij]` for active edges.
- `cfg`: `RicciFlowConfig(eta, eps_weight, eps_neck, preserve_total_edge_mass, preserve_connectedness, allow_disconnect, max_surgery_fraction)`.

## Outputs
- `discrete_ricci_flow_step` → `(N, N)` updated weights.
- `apply_neckpinch_surgery` → `(weights_after, tuple[NeckpinchEvent, ...])`.
- `ricci_flow_with_surgery` → `RicciFlowStepResult(weights_before, weights_after, curvature, surgery_events, total_edge_mass_before, total_edge_mass_after, surgery_event_count)`.
- Engine integration: `KuramotoRicciFlowEngine.run_with_surgery()` → `(KuramotoRicciFlowResult, KuramotoRicciFlowSurgeryDiagnostics)`.

## Invariants
- `INV-RC-FLOW`: post-step weights are finite, non-negative, symmetric, zero-diagonal; total mass is preserved when configured; bridges are clamped not removed under `preserve_connectedness=True`; surgery removal count ≤ cap.

## Tests
- `test_flow_preserves_symmetry_zero_diag_finiteness`
- `test_flow_preserves_total_edge_mass_when_enabled`
- `test_neckpinch_removes_non_bridge_edge` (K_4)
- `test_neckpinch_clamps_bridge_when_connectedness_required` (path graph)
- `test_surgery_fraction_cap`
- `test_integration_default_matches_previous_ricci_engine_behavior`
- `test_integration_enabled_records_surgery_events`
- `test_ricci_flow_deterministic`
- `test_eta_out_of_range_rejected`
- `test_detect_neckpinch_candidates_lex_order`
- `test_neckpinch_event_dataclass_immutable`

## Known limitations
- Implicit-Euler / variational schemes are not implemented; only explicit Euler.
- `eps_neck` defaults to a numerical tolerance, not a physical curvature scale.
- Bridge detection is recomputed each call via `networkx.bridges` (linear-time but not incremental).
- `allow_disconnect=True` exposes an escape hatch for callers who deliberately fragment the graph; it must be paired with `preserve_connectedness=False`.
- Curvature is supplied externally; the flow does not recompute it.

## No-alpha-claim disclaimer
This is a geometric primitive. No claim of trading edge or out-of-sample performance is made.

## Source anchor
arXiv:2510.15942 — Ollivier-Ricci flow with neckpinch surgery on NASDAQ-100.

## Iterated-Step Semantics (Known API Gap)

**Single-step contract (INV-RC-FLOW):** `ricci_flow_with_surgery` preserves finite/symmetric/non-negative
weights, mass (when enabled), and connectedness (when enabled). This contract was empirically
verified by the falsification battery (`falsify_ricci_surgery.py`): 6/7 PASS, single-step axes all
machine-precision.

**Iterated-step gap (NOT covered by INV-RC-FLOW):** repeated application of `ricci_flow_with_surgery`
on the same graph state with `preserve_total_edge_mass=True` and `preserve_connectedness=True`
DOES NOT preserve total edge mass or connectedness across iterations.

Empirical evidence (100 sequential steps, 20 ER graphs, N=10, eps_weight=1e-8):
- 8 / 20 final graphs disconnected (40%)
- max mass drift: ~100% (full mass leakage in worst case)
- median final edge count: 3

**Mechanism:** surgery clamps bridge candidates to `eps_weight` rather than removing them.
On the next iteration these clamped edges are re-flagged by `detect_neckpinch_candidates` (which
admits `0 < w ≤ eps_weight`). Once all incident edges of a node become clamped, the active-subgraph
definition shifts between `w > 0` (admits) and `w > eps_weight` (rejects), and `preserve_total_edge_mass`
re-normalizes mass away from these stub edges.

### Recommended Practice

- For **single-step research use**: the function works as documented. Use freely.
- For **multi-step iteration**: do NOT loop `ricci_flow_with_surgery` directly with default config.
  Use one of:
  1. Set `eps_weight=0.0` to make `detect_neckpinch_candidates` non-degenerate across iterations
     (at cost of: bridge candidates being fully removed instead of clamped, which can disconnect
     graphs faster — different trade-off, not better).
  2. Use the explicit `iterated_ricci_flow_with_surgery(weights, n_steps, cfg)` wrapper (added in
     this PR) which records mass-drift and connectedness state per step and aborts if invariants
     would be broken.
  3. Implement your own outer loop that re-asserts mass/connectedness manually between steps.

### Status

- 2026-04-25 — gap surfaced by falsification battery
- 2026-04-25 — documented as INV-RC-FLOW-ITER (P1, statistical) for future enforcement
- Open question: should this be promoted to a P0 universal invariant once the wrapper is in place?

