# D-002G-P3 — Phase 0 Discovery Report

> **Promise.** This report enumerates, for each prereg-scoped
> substrate, what node-payload and injection-sequence domains
> exist (or do not exist) under the locked API surface. It is a
> *factual* survey, not an admissibility verdict — the verdict is
> recorded in `D002G_P3_ELIGIBILITY_MATRIX.md` after the verifier
> runs against every cell.

## 1. Anchor

* Anchor commit (read-only): worktree branched off
  `2b3872c` (P2 head; PR #679 pre-merge).
* Branch: `feat/x10r-d002g-p3-constant-payload-null-recovery`.
* Locked governance verified byte-exact unchanged via existing
  `test_d002g_m2_locked_governance_untouched.py`.

## 2. Substrate-by-substrate domain survey

### 2.1 `ricci_flow` (Erdős-Rényi + Forman-Ricci)

| Domain candidate | Exists? | Topology decoupled? | Non-degenerate? | Notes |
|---|---|---|---|---|
| edge_weight | YES | YES | YES (≥ 2 distinct values: 3 / 8 / 10 distinct payloads at N=50/100/200) | P2 result — ELIGIBLE_M2. |
| node_payload (row-sum of ΔK) | YES (row-sum varies by degree) | NO — node identity ↔ ER adjacency. Permuting node IDs mutates K_baseline topology hash. | yes/no irrelevant once topology-coupled | TOPOLOGY_COUPLED. |
| injection_sequence (per-time-step events) | only one effective event (uniform lift across PRECURSOR_INJECTION_WINDOW = {4, 5}; both slices bit-identical) | n/a | NO — both events bit-identical | DEGENERATE. |

### 2.2 `block_structured` (tiered core / mid / periphery)

| Domain candidate | Exists? | Topology decoupled? | Non-degenerate? | Notes |
|---|---|---|---|---|
| edge_weight | yes (775 / 3100 / 12400 support entries at N=50/100/200) | yes | NO — 1 distinct value (single uniform inter-block lift `0.25·λ·K_c`) | DEGENERATE_SHUFFLE_POOL — P2 result. |
| node_payload (row-sum of ΔK) | yes (3 distinct values, one per block) | **NO** — block label assignment IS the topology semantic. Permuting node IDs relocates the inter-block lift to wrong (i, j) pairs and mutates ΔK topology hash. | irrelevant once topology-coupled | TOPOLOGY_COUPLED. |
| injection_sequence | exactly 2 events at t∈{4,5}, bit-identical | n/a | NO | DEGENERATE. |

### 2.3 `temporal_coupling` (block base + sinusoidal envelope)

| Domain candidate | Exists? | Topology decoupled? | Non-degenerate? | Notes |
|---|---|---|---|---|
| edge_weight | yes (1225 / 4950 / 19900 support entries) | yes | NO — 1 distinct value (uniform additive lift `0.15·λ·K_c`) | DEGENERATE_SHUFFLE_POOL. |
| node_payload (row-sum of ΔK) | yes (every node identical → 1 distinct value) | n/a | NO | DEGENERATE_POOL. |
| injection_sequence | exactly 2 events at t∈{4,5}, bit-identical AND coupled to sinusoidal envelope phase | n/a (would also be DEGENERATE) | NO | **CONTRACT_VIOLATION** — the substrate's stated lag-coupling contract (`K(t) = K_c · (1 + 0.20·sin(2π t / period))`) is the causal hypothesis itself. Permuting event order would emit a semantically-fake null. The verifier prioritises CONTRACT_VIOLATION over DEGENERATE so the failure mode is auditable. |

## 3. Summary of findings

* **No prereg substrate exposes a node-payload domain decoupled
  from topology.** Block labels (block_structured), random adjacency
  (ricci_flow), and uniform per-node intensity (temporal_coupling)
  all fail at least one of the three admissibility tests.
* **No prereg substrate exposes a non-degenerate injection
  sequence.** The current substrate API emits 2 identical events
  in the injection window; for `temporal_coupling` the temporal
  pattern is the substrate's identity (contract violation).

## 4. Implication for downstream PR

The P3 null-domain adjudication is structurally honest in the
NEGATIVE direction:

| Substrate | M1 | M2 edge | M2 node-payload | M2 injection-seq | FINAL DOMAIN |
|---|---|---|---|---|---|
| ricci_flow | ELIGIBLE | ELIGIBLE | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | M1 / M2_EDGE_WEIGHT |
| block_structured | INELIGIBLE | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED | INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE | **M3_REQUIRED** |
| temporal_coupling | INELIGIBLE | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL | INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION | **M3_REQUIRED** |

→ A fresh M3 pre-registration is required to bring
`block_structured` and `temporal_coupling` into the canonical run
admissibility envelope. PR-level pre-registration draft is
`D002G_P3_M3_PREREGISTRATION.md`.

B1 stays OPEN_PARTIAL (upgraded to OPEN_REQUIRES_M3). B2 is
untouched.
