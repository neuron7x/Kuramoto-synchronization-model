# D-002G — M2 Topology-Preserving Shuffle Null Mechanism

**Class.** Fallback null mechanism per `D002G_PREREGISTRATION.yaml §4`.
**Date.** 2026-05-13.
**Status.** Infrastructure. NOT a scientific PASS. NOT a canonical run.
NOT a D-002C rescue.

> This document specifies the M2 topology-preserving shuffle null
> mechanism. M2 is the pre-registered **fallback** for substrates
> that are M1-INELIGIBLE because their precursor / baseline matrices
> are seed-deterministic at λ=0. M2 ships as INFRASTRUCTURE — its
> presence in the repository establishes the ADMISSIBILITY of a
> non-degenerate null cohort on a wider set of substrates than M1
> can cover, but it does not by itself test any scientific
> hypothesis.

---

## 1. Why M2

D-002C attempt-2 was falsified by the executable null audit at the
9 λ=0 cells (`d002c_canonical_attempt_2_20260512T160318Z`). The
root cause was bit-identical paired CRN: at λ=0 the substrate
produced `K_precursor == K_baseline` byte-exact, the permutation
audit collapsed to `p=1.0`, and the verdict deriver emitted
`tier=D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET`.

D-002G replaced the bit-identical paired CRN with two mechanisms
locked at pre-registration merge:

* **M1 — independent-seed null cohort** (primary). Draws the null
  K_baseline at `seed = base_seed + null_seed_offset` (offset 10000).
* **M6 — placebo coupling** (supplementary R2-B gate).

P1 (PR #677) shipped both mechanisms + the Phase 0 verifier + the
R2-B aggregator. Phase 0 discovery surfaced a canonical-run
BLOCKER labelled **B1 — substrate eligibility** in
`D002G_CANONICAL_RUN_BLOCKERS.md`:

| Substrate id        | M1 eligibility   |
|---------------------|------------------|
| `ricci_flow`        | M1-ELIGIBLE      |
| `block_structured`  | M1-INELIGIBLE    |
| `temporal_coupling` | M1-INELIGIBLE    |

Two of three stock substrates ignore the seed argument at λ=0 by
construction. M1's contract — "draw the null at an independent
seed" — cannot apply: the substrate produces an identical
`K_baseline` regardless of the seed value.

The pre-registration §4 fallback policy locks **M2 — topology-
preserving shuffle** as the resolution path for B1.

---

## 2. Mechanism

For each `(substrate, N, λ, base_seed)`:

1. Compute the **precursor** at the locked injection window index:

   ```
   K_p = substrate.realize(N=N, lambda_=lambda_value, seed=base_seed)
   K_0 = substrate.realize(N=N, lambda_=0.0,          seed=base_seed)
   ΔK  = K_p[t_inj] − K_0[t_inj]
   ```

2. Build the **support mask** over the strict upper triangle:

   ```
   support_mask[i,j] = |ΔK[i,j]| > 1e-12   for i < j
   ```

   This is the **topology** of the precursor injection — the set of
   edges the substrate's locked mechanism touches (top-10% κ edges
   for Ricci, inter-block sub-blocks for block_structured, every
   off-diagonal edge for temporal_coupling).

3. Compute the **topology hash** as

   ```
   sha256(canonical_json({domain, N, mask_as_01_string}))
   ```

4. Seed the M2 RNG via

   ```
   null_seed = deterministic_mix(base_seed, M2_PLACEBO_SALT=211)
   rng       = np.random.default_rng(null_seed)
   ```

   `deterministic_mix` is the same sha256-based primitive M6 uses
   (per the P1 Strike-R5 attack rejection of arithmetic offsets).
   The salt `211` is a small prime, distinct from `M6_PLACEBO_SALT`
   (99) and from `NULL_SEED_OFFSET` (10000) — three orthogonal
   domain-separation tags so M1 / M6 / M2 RNG streams are
   statistically independent.

5. **Permute the payload, NOT the topology.** Extract the support
   payload values, permute via `rng.permutation`, reassign to the
   SAME support positions:

   ```
   vals             = ΔK[support_mask]              # |support| floats
   perm_vals        = rng.permutation(vals)         # same multiset
   ΔK_shuffled      = zeros(N,N)
   ΔK_shuffled[support_mask] = perm_vals            # same positions
   ΔK_shuffled      = symmetrise(ΔK_shuffled)
   K_null           = K_0 + ΔK_shuffled
   ```

6. **Verify topology invariance** by recomputing the hash on
   `ΔK_shuffled` and asserting it matches the precursor hash.
   Permutation within a fixed support set preserves the support
   mask by construction; the post-check guards against an
   implementation-level invariant break (e.g. if a future refactor
   accidentally introduced a non-trivial reindexing path).

### Mathematical invariants

| Property | Operator | Guarantee |
|---|---|---|
| Topology hash | `_topology_hash(ΔK)` | `pre == post` bit-identically |
| Edge count | `support_mask.sum()` | identical pre/post |
| Node count | `K.shape[0]` | identical (`N`) |
| Frobenius norm | `‖ΔK‖_F` | preserved to FP precision (sum-of-squares invariant under permutation) |
| Payload value multiset | `multiset(ΔK[support_mask])` | identical (permutation) |
| Payload assignment | `(i, j) → ΔK[i,j]` | **changed** whenever ≥ 2 distinct values exist |

### Why the multiset is preserved

Permutation is a bijection on the support index set. Each value in
the precursor's support payload re-appears at exactly one position
in the null's support payload, possibly the same position. The
multiset is therefore byte-equal across the two payloads, and so
is the Frobenius norm:

```
‖ΔK_p‖_F²  = Σ_{(i,j)∈support} ΔK_p[i,j]²
           = Σ_{(i,j)∈support} ΔK_null[i,j]²
           = ‖ΔK_null‖_F²
```

The DISTRIBUTION of payload values is the same; only their
SPATIAL ASSIGNMENT changes. This is the topology-preserving shuffle
contract.

---

## 3. Why M2 is NOT a scientific result

M2 ships **null-admissibility infrastructure**. It answers
exactly one empirical question:

> Is there a non-degenerate null cohort that can be constructed
> from this `(substrate, N, λ, seed)` while keeping the precursor
> topology fixed?

There are five possible answers, encoded as the
`M2EligibilityStatus` ladder. None of the five is a scientific
PASS for any D-002G hypothesis (G1, G2, G3, G4 from the
pre-registration). M2's verdict tells the operator whether the M2
fallback can construct an admissible null on this cell; it does
NOT measure precursor effect strength, false-positive rate,
direction stability, or any other R1/R2/R3/R2-B gate. Those
remain locked in `D002G_ACCEPTANCE_RULES.md` and are evaluated
ONLY when the canonical D-002G run is launched on a cell grid
where every cell has an admissible null mechanism (M1 or M2).

---

## 4. Eligibility verdict ladder

The verifier `verify_m2_eligibility(substrate, N, lambda_value,
base_seed, null_seed=None)` evaluates the cell and returns exactly
one of the following statuses. The ladder is short-circuit ordered
(first matching condition wins).

| # | Status | Trigger | Action |
|---|---|---|---|
| 1 | `INDETERMINATE_M2_PROVENANCE_MISSING` | `substrate.realize(...)` raised — the precursor itself is malformed | Escalate to the substrate owner; M2 cannot decide eligibility from a malformed precursor. |
| 2 | `INELIGIBLE_M2_INSUFFICIENT_TOPOLOGY` | `support_mask.sum() == 0` — no precursor delta at this `(N, λ, seed)` | M2 cannot preserve an empty topology. Use M1 at λ>0 if applicable, or escalate. |
| 3 | `INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL` | `support_mask.sum() ≥ 1` but `distinct_values_count < 2` | A permutation of one repeated value is a no-op. K_null would equal K_p bit-identically — exactly the pathology M2 was designed to remove. **REFUSED**. |
| 4 | `INELIGIBLE_M2_TOPOLOGY_MUTATION_DETECTED` | dry-run shuffle produced a different support-mask hash | Internal invariant break (should never fire under the current implementation). Cell **REFUSED** so the failure mode is observable rather than silent. |
| 5 | `ELIGIBLE_M2` | all of (1)–(4) pass | The cell admits a non-degenerate M2 null. `realize_null(strategy="M2_TOPOLOGY_PRESERVING_SHUFFLE", ...)` will succeed. |

### Empirical per-substrate verdict at the canonical grid

| Substrate | N=50 | N=100 | N=200 | Reason |
|---|---|---|---|---|
| `ricci_flow` | ELIGIBLE_M2 | ELIGIBLE_M2 | ELIGIBLE_M2 | Forman-Ricci κ varies across edges → multi-valued ΔK payload |
| `block_structured` | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | additive inter-block lift is a single constant `0.25·λ·K_c` |
| `temporal_coupling` | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | additive lift is a single constant `0.15·λ·K_c` across every off-diagonal edge |

These verdicts are FACTS about the stock substrates, not bugs in
M2. The edge-weight shuffle domain cannot reduce the constant-
valued ΔK to a non-degenerate null because there is no
within-support payload entropy to redistribute. **B1 is therefore
PARTIALLY MITIGATED — only the `ricci_flow` cell becomes
admissible under M2 edge-weight shuffle. `block_structured` and
`temporal_coupling` remain HARD-BLOCKED for the canonical D-002G
run under the current `(M1, M2_edge_weight)` toolkit.**

Future work: investigate node-payload and injection-sequence
shuffle sub-domains (reserved by `M2EligibilityVerdict.
shuffle_domain ∈ {"node_payload", "edge_weight",
"injection_sequence"}`). These are NOT implemented in this PR.

---

## 5. Determinism contract

The M2 mechanism is bit-identically deterministic. Given the
locked tuple

```
(substrate_id, N, lambda_value, base_seed, null_seed)
```

with `null_seed = deterministic_mix(base_seed, M2_PLACEBO_SALT)`
under the locked formula, two invocations of `realize_null` produce:

* identical `K_baseline` arrays (byte-equal `numpy.tobytes()`),
* identical `payload_sha256`,
* identical `preserved_topology_hash`,
* identical `null_seed`,
* identical `candidate_pool_size`,
* identical metadata payload (except `generated_at` which is
  wallclock and excluded from the sha).

The implementation uses `np.random.default_rng(null_seed)` with NO
global state read. No `random.random()`. No time-based seeds. No
`SeedSequence.spawn` (locked to the verifier-emitted seed value so
the test-suite can pin payload shas).

---

## 6. Forbidden interpretations

This section lists the forbidden statements about M2. The strings
appear inside fences so the no-scientific-PASS-claim test sees
them in their negation context.

❌ "M2 PASS = D-002G scientific PASS."

   M2 establishes admissibility, not a scientific verdict. The
   D-002G acceptance ladder (R1 ∧ R2 ∧ R3 ∧ R2-B ∧ NULL_AUDIT)
   is evaluated by the verdict deriver after a canonical run; M2
   is a precondition for the canonical run on M1-INELIGIBLE
   substrates, not a substitute for the acceptance ladder.

❌ "M2 unblocks canonical run by itself."

   M2 partially mitigates blocker B1 in the canonical-run
   blockers manifest. B2 (percentile-CI limitation on Phase 0b)
   remains; any future blocker remains. The canonical D-002G run
   is BLOCKED on the AND-conjunction of B1, B2, and any future
   blocker — relaxing one term does not relax the conjunction.

❌ "M2 replaces M1 for ricci_flow."

   M1 stays primary on the substrate where it is ELIGIBLE
   (ricci_flow). M2 is the fallback for substrates where M1
   cannot apply (block_structured, temporal_coupling — currently
   INELIGIBLE under M2 edge-weight as well). The canonical run
   uses M1 wherever M1 is admissible.

❌ "M2 lifts D-002C attempt-2 falsification."

   No. D-002C attempt-2 is preserved append-only in the D-002C
   claim ledger. M2 is part of the SEPARATE D-002G contract.

❌ "M2 enables D-002C rescue."

   No. D-002G does not rescue D-002C. The two are independent
   contracts with independent run reports, independent ledger
   entries, and independent claim boundaries. M2's existence in
   the repository is invisible to the D-002C claim layer.

---

## 7. Relationship to existing locked governance

M2 LIVES INSIDE the D-002G contract surface; it does not mutate
it. The relevant relationships:

* `D002G_PREREGISTRATION.yaml` (locked at PR #676 merge,
  sha256 `1ab91f09...`):
  * §4 `null_mechanism.fallback = M2` (already pre-registered).
  * `null_mechanism.fallback_description`: "Topology-preserving
    shuffled null. Used only if Phase 0 verification fails for
    M1. Substrate generates a degree-sequence-preserving rewired
    graph for the null cohort." (lines 116–121).
  * `null_mechanism.forbidden` explicitly bans bit-identical
    paired CRN (line 123). M2's contract honours this — the M2
    shuffle re-permutes payload values within a fixed support
    set, so K_null ≠ K_p whenever ≥ 2 distinct values exist.
  * `phase_0_verification.fail_action`: "If M1 fails Phase 0,
    fall back to M2 (topology-preserving shuffle) and restart
    Phase 0." (lines 204–208). M2 is the named successor under
    Phase 0 failure.

* `D002G_NONDEGENERATE_NULL_DESIGN.md` (locked, sha256
  `9cef2db7...`):
  * §3 line 72: "M2 Topology-preserving shuffled null —
    ✓ graph edges rewired with degree preservation — ✓ degree
    sequence preserved (mean coupling same) — Requires new
    substrate `realize_shuffled` API". M2 lands the equivalent
    primitive at the higher-level `realize_null(strategy="M2_*")`
    boundary so the existing substrate API stays untouched —
    P1's `Substrate` Protocol is consumed read-only.
  * §3 line 94: "Fallback mechanism: M2 (topology-preserving
    shuffle) if M1+M6 empirically fail Phase 0 verification."

* `D002G_ACCEPTANCE_RULES.md` (locked, sha256 `875b1e3e...`):
  * §4 Phase 0 acceptance ladder: "If ANY cell fails → Phase 0
    FAIL → fall back to mechanism M2 (topology-preserving
    shuffle) and restart Phase 0; if M2 also fails, escalate to
    a new pre-registration (not edit)." (lines 148–150). M2 is
    the named fallback; this PR implements the named fallback.

None of those files are mutated by the M2 PR. The canonical-run
blockers manifest (`D002G_CANONICAL_RUN_BLOCKERS.md`) IS updated
to record the M2 mitigation status — that file is NOT in the
locked-files registry (it was added during P1, after the
pre-registration anchor).

---

## 8. Scope boundary (re-asserted)

This document plus the M2 implementation establish:

* ✓ A topology-preserving shuffle null mechanism (M2) is
  available on the `Substrate` Protocol API.
* ✓ A pre-check verifier emits one of five verdicts per cell.
* ✓ A fail-closed realisation layer refuses non-ELIGIBLE cells
  without silent downgrade.
* ✓ Determinism contract is enforced byte-equally per
  `(base_seed, null_seed, N, λ, substrate_id)`.
* ✓ Topology, edge count, node count, Frobenius norm, payload
  multiset are M2-invariants.
* ✓ B1 partial-mitigation status is recorded in
  `D002G_CANONICAL_RUN_BLOCKERS.md`.

This document plus the M2 implementation do NOT establish:

* ❌ a D-002G scientific PASS,
* ❌ a canonical D-002G run start,
* ❌ a D-002G tier promotion to `SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN`,
* ❌ a D-002C cross-promotion,
* ❌ a D-002C ledger mutation,
* ❌ a B1 full-CLOSURE (only `ricci_flow` becomes ELIGIBLE under
  M2 edge-weight; the other two substrates remain HARD-BLOCKED
  under this PR's M2 sub-domain).

The canonical D-002G run remains BLOCKED on the AND-conjunction
of B1 (substrate eligibility — partially mitigated) AND B2
(percentile-CI limitation) AND any future blocker.
