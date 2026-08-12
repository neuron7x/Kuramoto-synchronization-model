# D-002G-P3 — Null-domain admissibility contracts

> **Contract source.** This document is the law that the P3
> verifier code MUST honour. Code that drifts from this contract
> is a bug; this doc is read-only with respect to a future PR's
> implementation review.

## 1. Universe of candidate domains

| Domain | Substrate-side anchor | Verifier function |
|---|---|---|
| `edge_weight` | upper-triangle ΔK payload multiset | `verify_m2_eligibility` (P2) |
| `node_payload` | per-node attribute (row-sum of ΔK as fallback) | `verify_m2_node_payload_eligibility` (P3) |
| `injection_sequence` | per-time-step (t, ΔK(t)) tuples within the injection window | `verify_m2_injection_sequence_eligibility` (P3) |
| `M3-topology-conditioned` | future / pre-registered separately | n/a (P3 does not implement) |

## 2. Admissibility requirements (per domain)

### 2.1 edge_weight (recap — P2)

1. ΔK upper-triangle support ≥ 1.
2. Distinct payload values across support ≥ 2.
3. Dry-run permutation preserves topology hash.

### 2.2 node_payload (P3)

1. Substrate constructs without raising → otherwise
   `INDETERMINATE_M2_NODE_PAYLOAD_PROVENANCE_MISSING`.
2. Per-node payload vector has at least one nonzero entry →
   otherwise `INELIGIBLE_M2_NODE_PAYLOAD_MISSING_DOMAIN`.
3. Per-node payload pool has ≥ 2 distinct values → otherwise
   `INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL`.
4. A non-identity node permutation MUST preserve both the
   K_baseline topology hash AND the ΔK topology hash →
   otherwise `INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED`.

### 2.3 injection_sequence (P3)

1. Substrate constructs without raising → otherwise
   `INDETERMINATE_M2_INJECTION_SEQUENCE_PROVENANCE_MISSING`.
2. The substrate emits ≥ 2 discrete injection events in the
   canonical injection window → otherwise
   `INELIGIBLE_M2_INJECTION_SEQUENCE_MISSING_DOMAIN`.
3. The substrate does NOT stake a lag-coupling contract on event
   order (semantic invariant). For `temporal_coupling` the
   sinusoidal envelope IS the contract → therefore
   `INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION`.
4. Events are not pairwise bit-identical → otherwise
   `INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE`.

## 3. Preservation invariants

All four sub-domains share the M2 family invariants:

* **TopoH** Topology hash of K_baseline (and of ΔK) is invariant
  under the chosen permutation. Hash drift ⇒ REFUSE fail-closed.
* **Det** RNG seeded by `np.random.default_rng(deterministic_mix
  (base_seed, salt))`. No global state. No `random.random()`. No
  time-based seeds.
* **Multiset** Permutation preserves the payload multiset by
  construction (no resampling, no replace).
* **Stamp** `NullRealization.metadata` carries the verdict status
  literal, the shuffle_domain literal, the preserved topology
  hash, the null_seed used, the support_count, and the
  injection_window_index.

## 4. Failure verdicts (exhaustive enumeration)

| Sub-domain | Verdict literal | Promotion allowed? |
|---|---|---|
| edge_weight | ELIGIBLE_M2 | YES — to realisation; never to scientific PASS |
| edge_weight | INELIGIBLE_M2_INSUFFICIENT_TOPOLOGY | NO |
| edge_weight | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | NO |
| edge_weight | INELIGIBLE_M2_TOPOLOGY_MUTATION_DETECTED | NO |
| edge_weight | INDETERMINATE_M2_PROVENANCE_MISSING | NO |
| node_payload | ELIGIBLE_M2_NODE_PAYLOAD | YES — to realisation only |
| node_payload | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | NO |
| node_payload | INELIGIBLE_M2_NODE_PAYLOAD_MISSING_DOMAIN | NO |
| node_payload | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | NO |
| node_payload | INDETERMINATE_M2_NODE_PAYLOAD_PROVENANCE_MISSING | NO |
| injection_sequence | ELIGIBLE_M2_INJECTION_SEQUENCE | YES — to realisation only |
| injection_sequence | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | NO |
| injection_sequence | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | NO |
| injection_sequence | INELIGIBLE_M2_INJECTION_SEQUENCE_MISSING_DOMAIN | NO |
| injection_sequence | INDETERMINATE_M2_INJECTION_SEQUENCE_PROVENANCE_MISSING | NO |

## 5. Explicit forbidden promotions

NO null-domain admissibility verdict may promote to:

* D-002G scientific PASS (any claim string from the forbidden-
  phrase list).
* canonical D-002G run authorisation.
* tier promotion at the D-002C ledger.
* D-002C rescue claim.

These promotions require ADDITIONAL artefacts that this PR does
NOT issue.

## 6. B1 ELIGIBILITY CLOSURE — AND-conjunction

B1 (substrate eligibility) closes IFF, simultaneously, for every
prereg-scoped substrate `s ∈ {ricci_flow, block_structured,
temporal_coupling}`:

```
∃ domain d ∈ {edge_weight, node_payload, injection_sequence, M3-*}.
verify_m2_*_eligibility(s, d) == ELIGIBLE_*
```

If even one substrate has no ELIGIBLE domain across the surface,
B1 stays OPEN.

## 7. Canonical-run authorisation — AND-conjunction

```
canonical_run_authorized
    ↔   (B1 closed for eligibility-only)
        AND (B2 closed or scoped-accepted)
        AND (no future blocker exists)
        AND (explicit canonical-run authorization artifact exists)
```

NONE of these conjuncts can be satisfied by this PR. P3 produces
ZERO `canonical_run_authorized` claims.
