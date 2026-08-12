# D-002G-M3 — Null-domain eligibility matrix

> Generated via `verify_m3_eligibility` against the locked prereg
> grid `λ=0.4, base_seed=42, null_seed=12345`, salt 523.
> Machine-readable sibling: `artifacts/d002g/m3/m3_null_domain_verdicts.json`.
>
> M3 pre-registration anchor: PR #680 (sha
> `0f4433e04c7a594fc80c964eeec337a8b1128038`),
> `docs/governance/D002G_P3_M3_PREREGISTRATION.md`.

## 1. Scope

| Parameter | Value | Source |
|---|---|---|
| `lambda_value` | 0.4 | locked pre-registration |
| `base_seed` | 42 | locked pre-registration |
| `null_seed` | 12345 | P3 test-suite override (carries from P3 PR) |
| `N` | {50, 100, 200} | locked prereg N_grid |
| Substrates | `ricci_flow`, `block_structured`, `temporal_coupling` | locked prereg substrate registry |
| `M3_TOPOLOGY_CONDITIONED_SALT` | 523 | locked at M3 pre-reg §9 |

## 2. Tolerance constants (declared BEFORE results, per M3 pre-reg §9.1)

| Tolerance | Value | Purpose |
|---|---:|---|
| `tol_marginal` | 0.05 | general marginal-match band |
| `tol_non_degenerate` | 1e-3 | min Frobenius distance ‖K_null − K_p‖ |
| `tol_density` | 0.02 | density relative-error band |
| `tol_spectral_radius` | 0.05 | spectral_radius/N relative-error band |
| `tol_degree_wasserstein` | 0.05 | normalised degree-sequence Wasserstein-1 band |

## 3. Verdict matrix

For each substrate × N cell. M1 / M2_EDGE_WEIGHT / M2_NODE_PAYLOAD /
M2_INJECTION_SEQUENCE verdicts carried from prior P1 / P2 / P3 ledgers
(NOT re-evaluated in this PR — re-evaluating would constitute a canonical
substrate sweep, outside M3 scope).

| Substrate | N | M1 | M2_EDGE_WEIGHT | M2_NODE_PAYLOAD | M2_INJECTION_SEQUENCE | M3 | FINAL_NULL_DOMAIN | B1 contribution |
|---|---:|---|---|---|---|---|---|---|
| `ricci_flow` | 50 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | ELIGIBLE_M3 | M1 | ELIGIBLE |
| `ricci_flow` | 100 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | ELIGIBLE_M3 | M1 | ELIGIBLE |
| `ricci_flow` | 200 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | ELIGIBLE_M3 | M1 | ELIGIBLE |
| `block_structured` | 50 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | M4_REQUIRED | INELIGIBLE |
| `block_structured` | 100 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | M4_REQUIRED | INELIGIBLE |
| `block_structured` | 200 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | M4_REQUIRED | INELIGIBLE |
| `temporal_coupling` | 50 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | M4_REQUIRED | INELIGIBLE |
| `temporal_coupling` | 100 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | M4_REQUIRED | INELIGIBLE |
| `temporal_coupling` | 200 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | M4_REQUIRED | INELIGIBLE |

## 4. B1 closure status

| Substrate | Has ELIGIBLE domain across {M1, M2 edge, M2 node, M2 inj, M3}? |
|---|---|
| `ricci_flow` | yes (M1, M2 edge_weight, M3) |
| `block_structured` | NO (all five domains INELIGIBLE) |
| `temporal_coupling` | NO (all five domains INELIGIBLE) |

Per `D002G_P3_NULL_DOMAIN_CONTRACTS.md §6` and the §11 closure rule,
B1 closes IFF every substrate has at least one ELIGIBLE domain. Two
substrates still have NONE after M3 lands → **B1 does NOT close**;
B1 stays `OPEN_REQUIRES_M4`.

## 5. Decision state

→ **`M3_INELIGIBLE_M4_REQUIRED`**

The M3 mechanism family — topology-conditioned independent realisation
under matched-density resampling — is INELIGIBLE on both M1-blocked
substrates. Root cause: their precursor lift is seed-deterministic by
construction (`block_structured` has a fixed inter-block lift; the
`temporal_coupling` inherits this lift and adds a deterministic
sinusoidal envelope), so the M3 topology summary is seed-invariant.
Criterion 3 (`Identifiable from precursor`) refuses the cell
fail-closed: 0 / 99 adjacent-seed precursor pairs yield distinct
degree marginals, well below the required ≥ 50 / 99.

The honest INELIGIBLE_M3 verdict IS the scientific result here. A
forced ELIGIBLE_M3 would have demanded post-hoc relaxation of either
the precursor-specificity criterion or the locked tolerances; both
are explicitly forbidden by M3 pre-reg §9.1.

## 6. Forbidden interpretations

The verdict `M3_INELIGIBLE_M4_REQUIRED` does NOT imply:

* a D-002G PASS claim of any kind;
* a D-002C ledger rescue;
* a canonical run authorisation;
* a tier promotion for any substrate;
* a B2 closure (B2 remains OPEN as a separate, untouched blocker).

It records the structural fact that the M1 ∪ M2 ∪ M3 admissibility
surface still excludes two prereg substrates on the locked grid, and
points the next PR at a fresh M4 mechanism pre-registration. The
honest INELIGIBLE verdict IS the scientific result; canonical D-002G
remains BLOCKED on the AND-conjunction of B1 (substrate eligibility —
upgraded `OPEN_REQUIRES_M3 → OPEN_REQUIRES_M4`) AND B2 (percentile-CI
limitation) AND any future blocker.

## 7. Claim boundary (verbatim)

> This PR implements M3 null-admissibility infrastructure only. It
> does NOT establish D-002G scientific PASS. It does NOT authorise
> canonical D-002G run. It does NOT close B2. It does NOT update
> D002C_CLAIM_LEDGER.yaml. M3 eligibility alone is not canonical-run
> authorisation.
