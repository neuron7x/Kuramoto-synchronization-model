# D-002G-P3 — Null-domain eligibility matrix

> Generated via `verify_m2_*_eligibility` against the locked prereg
> grid `λ=0.4, base_seed=42, null_seed=12345`. Machine-readable
> sibling: `artifacts/d002g/p3/null_domain_verdicts.json`.

## 1. Scope

| Parameter | Value | Source |
|---|---|---|
| `lambda_value` | 0.4 | locked pre-registration |
| `base_seed` | 42 | locked pre-registration |
| `null_seed` | 12345 | P3 test-suite override |
| `N` | {50, 100, 200} | locked prereg N_grid |
| Substrates | `ricci_flow`, `block_structured`, `temporal_coupling` | locked prereg substrate registry |

## 2. Verdict matrix

For each substrate × N cell. M1 verdict carried from prior P1
ledger (not re-evaluated in this PR — running M1 would constitute
a canonical-substrate sweep, outside P3 scope).

| Substrate | N | M1 | M2_EDGE_WEIGHT | M2_NODE_PAYLOAD | M2_INJECTION_SEQUENCE | FINAL_NULL_DOMAIN | B1 contribution |
|---|---:|---|---|---|---|---|---|
| `ricci_flow` | 50 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M1 | ELIGIBLE |
| `ricci_flow` | 100 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M1 | ELIGIBLE |
| `ricci_flow` | 200 | ELIGIBLE_M1 | ELIGIBLE_M2 | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M1 | ELIGIBLE |
| `block_structured` | 50 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `block_structured` | 100 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `block_structured` | 200 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `temporal_coupling` | 50 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `temporal_coupling` | 100 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | M3_REQUIRED | INELIGIBLE_M2_FULL |
| `temporal_coupling` | 200 | INELIGIBLE_M1_BIT_IDENTICAL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | M3_REQUIRED | INELIGIBLE_M2_FULL |

## 3. B1 closure status

| Substrate | Has ELIGIBLE domain? |
|---|---|
| `ricci_flow` | yes (M1, M2 edge_weight) |
| `block_structured` | NO across all four M1/M2 domains |
| `temporal_coupling` | NO across all four M1/M2 domains |

Per the contract in `D002G_P3_NULL_DOMAIN_CONTRACTS.md §6` and the
§11 closure rule, B1 may close IFF every substrate has at least
one ELIGIBLE domain. Two substrates have NONE → **B1 does NOT
close**; B1 is upgraded from `OPEN_PARTIAL` to `OPEN_REQUIRES_M3`.

## 4. P3 decision state

→ **`P3_M3_PREREGISTRATION_REQUIRED`**

The eligibility surface is exhausted on the M1/M2 stack for two
substrates. A fresh M3 mechanism family must be pre-registered;
see `D002G_P3_M3_PREREGISTRATION.md` for the draft pre-reg.

## 5. Forbidden interpretations of this matrix

The verdict `M3_REQUIRED` does NOT imply:

* a D-002G PASS claim of any kind;
* a D-002C ledger rescue;
* a canonical run authorisation;
* a tier promotion for any substrate.

It records the structural fact that the M1 ∪ M2 admissibility
surface excludes two prereg substrates on the locked grid, and
points the next PR at a pre-registered M3 mechanism. The honest
INELIGIBLE verdict IS the scientific result here.
