# Sparse simplicial higher-order Kuramoto

**Status.** Experimental, opt-in. Existing `HigherOrderKuramotoEngine` and helpers (`find_triangles`, `build_triangle_index`) are unchanged; the sparse path is purely additive.

## Implemented files
- `core/physics/higher_order_kuramoto.py` (additive symbols listed below)
- `tests/unit/physics/test_higher_order_kuramoto_sparse.py`

## Formula

For each triangle `(i, j, k)` in the 2-simplex skeleton:

```
Δθ̇_i += sin(2θ_j − θ_k − θ_i)
Δθ̇_j += sin(2θ_i − θ_k − θ_j)
Δθ̇_k += sin(2θ_i − θ_j − θ_k)
```

Total triadic RHS = `sigma2 · (Δθ̇)`. Pairwise term unchanged.

Implementation uses `numpy.add.at` for deterministic per-node accumulation; no `O(N²)` or `O(N³)` auxiliary buffers are allocated.

## Inputs
- `adj`: `(N, N)` boolean adjacency.
- `theta`: `(N,)` phase vector.
- `cfg`: `HigherOrderSparseConfig(sigma1, sigma2, max_triangles, dense_debug)`.
- `dt`, `steps` for the integrator helper `run_sparse_higher_order`.

## Outputs
- `build_sparse_triangle_index(adj, max_triangles=None)` → `SparseTriangleIndex(i, j, k, n_nodes)`.
- `triadic_rhs_sparse(theta, index, sigma2)` → `(N,)` float64.
- `run_sparse_higher_order(adj, omega, theta0, cfg, dt, steps)` → `HigherOrderKuramotoResult`.
- `validate_sparse_triangle_index(index)` raises on any violation.

## Invariants
- `INV-HO-SPARSE`: `R(t) ∈ [0,1]` over the trajectory; `sigma2=0` ⇒ zero triadic RHS; sparse triangle count agrees with dense reference engine on small graphs; deterministic under fixed inputs; no `O(N³)` allocation when `dense_debug=False`.

## Tests
- `test_sparse_triangle_index_unique_sorted`
- `test_sparse_matches_existing_dense_on_small_complete_graph`
- `test_sigma2_zero_matches_pairwise`
- `test_no_triangles_zero_triadic`
- `test_R_bounds_sparse`
- `test_sparse_deterministic`
- `test_large_sparse_graph_does_not_use_dense_N3_path` (≤1 MB peak heap on N=120; vs ~13.8 MB for an O(N³) tensor)
- `test_validate_sparse_triangle_index_rejects_unsorted`
- `test_max_triangles_cap_enforced`
- `test_sparse_config_validation`

## Known limitations
- Triadic structure is fixed at 2-simplex (triangles); 3-simplices and higher are not provided.
- The `max_triangles` cap is a hard error, not a sampling fallback.
- `numpy.add.at` is deterministic but not parallelised; very large triangle counts will be CPU-bound.
- Dense vs sparse comparison test compares triangle counts and order-parameter bounds rather than full trajectory equality, because the dense engine multiplies by `|corr|` while the sparse engine uses unit boolean weights — a deliberate choice to keep the sparse path independent of correlation magnitude.

## No-alpha-claim disclaimer
This is an experimental simplicial primitive. No claim of trading edge or out-of-sample performance is made.

## Source anchor
PRR 2025 (10.1103/PhysRevResearch.7.023103) and arXiv:2011.00897 — explosive higher-order Kuramoto on simplicial complexes.
