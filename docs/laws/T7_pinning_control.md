# GeoSync Physics Law T7 — Operational Pinning Control of Chaos

**Status:** ACTIVE • **Tier:** ANCHORED on Wang-Chen (2002); Sorrentino et al. (2007); Olfati-Saber & Murray (2004)
**Module:** `runtime/pinning_control.py`
**Tests:** `tests/unit/physics/test_T7_pinning_control.py`

---

## 1. Statement

For a diffusively-coupled network with graph Laplacian `L = D − A`, choose a *pinned subset* `P ⊂ V` and apply uniform-gain feedback only to those nodes:

```
u_i(t)  =  −γ · (x_i(t) − x_target_i)   for i ∈ P
u_i(t)  =  0                             otherwise.
```

The closed-loop dynamics

```
ẋ  =  f(x)  −  L · x  −  Γ_P · (x − x_target),    Γ_P = γ · diag(1_P)
```

synchronise to the target iff the *augmented Laplacian's algebraic connectivity* is positive:

```
λ_2(L + Γ_P)  >  ε_pin.            (gain margin, INV-PIN1)
```

The pinned set `P` is selected **greedily** to maximise `λ_2(L + Γ_P)` in O(N²·k) time. Deterministic for given `(A, gain, ε_pin, k_max)`. No black-box. No learned model. **Self-contained physics-based controller.**

This is the constitutional T7 ban: Layer 4 (Processing) controls deterministic chaos in real-time *without external models*. It is a hard architectural rule, not a recommendation.

## 2. Public surface

| Symbol | Role |
|---|---|
| `graph_laplacian(A)` | `L = D − A` for symmetric, non-negative `A` |
| `algebraic_connectivity(A)` | Fiedler eigenvalue λ_2(L); INV-SG2 compat |
| `pinning_gain_margin(A, P, γ)` | `λ_2(L + Γ_P)` |
| `select_pinning_set(A, *, gain, eps_pin, k_max=None)` | Greedy P, returns `PinningReport(status, pinned_indices, gain_margin, iterations)` |
| `pinning_step(x, *, A, pinned_indices, gain, target=None, dt)` | One explicit-Euler step of the closed-loop flow |
| `PinningStatus` | Enum: `SUFFICIENT` or `INSUFFICIENT` |
| `PinningReport` | NamedTuple |

Pure NumPy. No I/O. No state. No JAX dependency.

## 3. Constitutional invariants (P0)

```
INV-PIN1 | universal   | returned P satisfies λ_2(L + Γ_P) > ε_pin OR    | P0
                       | status == INSUFFICIENT. Fail-closed.
INV-PIN2 | conditional | pinning_step contractive in linearised regime: | P0
                       | ||x||² strictly decreases when target=0,
                       | λ_2(L+Γ_P) > 0, dt < 2/λ_max(L+Γ_P).
INV-PIN3 | universal   | A is never mutated. Topology of unpinned       | P0
                       | subgraph preserved by construction.
INV-PIN4 | universal   | every contract violation → ValueError;         | P0
                       | fail-closed (non-square A, signed A, gain ≤ 0,
                       | ε_pin < 0, k_max ∉ [1,N], dt ≤ 0, shape
                       | mismatch, out-of-range pin indices).
```

## 4. Falsification battery (23 tests, 100 % green)

| Test | What it catches if it fires |
|---|---|
| `test_graph_laplacian_complete_graph_eigvals_match_textbook` | Laplacian off by spectral characterisation |
| `test_algebraic_connectivity_complete_graph_equals_N` | Fiedler eigenvalue computation drifts |
| `test_algebraic_connectivity_path_graph_positive` | path P_n misclassified as disconnected |
| `test_algebraic_connectivity_disconnected_graph_zero` | INV-SG2 (compat) violated |
| `test_INV_PIN1_returns_sufficient_with_enough_gain` | strong gain fails to drive margin > ε_pin |
| `test_INV_PIN1_returns_insufficient_when_gain_too_small` | tiny gain misreported as SUFFICIENT (fail-closed) |
| `test_INV_PIN1_pinning_one_node_complete_graph_sufficient` | K_N pinning one node fails to give λ_2 ≥ 1 |
| `test_INV_PIN2_pinning_step_contractive_with_zero_target` | controller does not contract under valid stability bound |
| `test_INV_PIN2_no_pinning_yields_no_contraction_to_target` | negative control: proves contraction is due to pinning |
| `test_INV_PIN3_topology_preserved_outside_pinned_set` | A is mutated by select / step (would break audit) |
| `test_INV_PIN4_*` (8 contract checks) | silent input repair |
| `test_INV_HPC1_select_pinning_set_repeatable` | greedy non-determinism |
| `test_negative_control_select_does_not_pin_all_nodes_when_unnecessary` | greedy vacuously pins all N (would make law trivially "true") |

## 5. Industrial acceptance conditions

T7 is a law (not a feature) when **all six** are true:

1. ✅ Pure functional; no JAX dependency at runtime; no I/O; no state.
2. ✅ `mypy --strict --follow-imports=silent` clean; `ruff` clean; `black --check` clean.
3. ✅ All 23 falsification tests pass.
4. ✅ Determinism by construction (greedy on a deterministic objective).
5. ✅ Acceptor YAML recorded; this report path published; INVARIANT REGISTRY updated.
6. ⏳ INVENTORY-hash and module-routing in `CLAUDE.md` updated (administered at PR merge).

## 6. Use in the stack

* **Layer 4 (Processing).** GeoSync orchestrator gains an internal physical controller of chaos. Zero external ML in the control loop — it is a constitutional ban, not a recommendation.
* **Composes with T1.** Pinning is meaningful only when the synchronised manifold exists, which requires Φ > 0 (Law T1, INV-KR1). T1 is the *necessary* condition; T7 INV-PIN1 is the *sufficient* gain margin.
* **Composes with T3.** A CONVERGED `K*` from T3 is a precondition; activating pinning on an uncalibrated coupling is forbidden.
* **Composes with T5.** Pinning energy ≤ Landauer budget — T5 sets the ceiling on how much state correction the controller can afford.
* **Composes with Layer 0/1.** With pinning active, the gradient is sustained by physics, not by external models — the controller IS a sustainer in the gradient ontology of CLAUDE.md §0.

## 7. References

* Wang, X. F.; Chen, G. (2002). *Pinning control of scale-free dynamical networks.* Physica A **310**, 521–531.
* Sorrentino, F. et al. (2007). *Controllability of complex networks via pinning.* Phys. Rev. E **75**, 046103.
* Olfati-Saber, R.; Murray, R. M. (2004). *Consensus problems in networks of agents with switching topology and time-delays.* IEEE Trans. Autom. Control **49**, 1520–1533.
