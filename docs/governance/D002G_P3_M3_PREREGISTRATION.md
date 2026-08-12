# D-002G-P3 — M3 Pre-Registration Draft

> **Pre-registration discipline.** M3 pre-registration is locked
> at the merge commit of this PR; subsequent edits constitute a
> fresh M4 pre-registration. The mechanism, admissibility
> criteria, expected invariants, failure states, negative controls,
> and forbidden interpretations below are the LAW any future M3
> implementation PR must honour.

## 1. Background

P3 found that **no M1 / M2-edge-weight / M2-node-payload /
M2-injection-sequence sub-domain admits the `block_structured` or
`temporal_coupling` substrates** on the locked prereg grid.
Eligibility surface is exhausted. Either:

* the canonical D-002G run scope must be narrowed to
  `ricci_flow`-only (NOT permitted: prereg scopes 3 substrates), OR
* a fresh M3 mechanism family must be pre-registered (this doc).

## 2. M3 mechanism family — proposed scope

Working title: **M3 — topology-conditioned independent realisation
under matched-density resampling**.

Core idea: instead of permuting payload values WITHIN a fixed
substrate realisation (the M2 contract), M3 constructs the null
cohort by drawing an INDEPENDENT realisation from a TOPOLOGY-MATCHED
generator whose marginals match the precursor's marginals at the
canonical injection slice.

Concretely, the implementation PR may refine only implementation details
inside the locked M3 family below. It may NOT change the mechanism family,
admissibility criteria, failure states, negative controls, forbidden
interpretations, or RNG salt without creating a fresh M4 pre-registration.

```
M3.realize_null(substrate, base_seed, null_seed, λ, N):
    K_p = substrate.realize(N, λ, base_seed).K_precursor[t_inj]
    # Match: degree sequence, block label histogram, spectral
    # radius / N, density. NOT: pointwise payload values.
    K_null = topology_matched_resample(K_p, null_seed)
    return K_null with stamped provenance
```

The match-set is what distinguishes M3 from M1: M1 draws an
independent realisation at λ AND propagates the precursor injection
on a fresh seed; M3 draws an independent realisation conditioned
on the SAME topology summary as the precursor's K_precursor[t_inj]
(no precursor propagation — the conditioning IS the topology
constraint).

## 3. Admissibility criteria

A substrate is M3-ADMISSIBLE iff:

| Criterion | Concrete test |
|---|---|
| **Topology marginal extractable** | Substrate exposes degree sequence / block-label histogram / spectral radius / density from its `SubstrateRealization`. |
| **Matched generator exists** | There is a deterministic-RNG-seedable generator that emits a (T, N, N) K matching the marginals to within `tol_marginal`. |
| **Identifiable from precursor** | The matched marginals are PRECURSOR-SPECIFIC: a different precursor seed yields different marginals at probability ≥ 0.5 over an ensemble of 100 seeds. |
| **Non-degenerate distance** | `||K_null − K_p||_F > tol_non_degenerate` at locked tolerance. |
| **Topology-coupling decoupled** | A non-identity node-permutation of K_null preserves the marginal histogram (this is the M3 invariant — necessary, not sufficient). |

If any of the five fails, M3 is INELIGIBLE for that substrate and
M4 is required.

## 4. Expected invariants

| Invariant | Description |
|---|---|
| **M3-INV-1** | `np.random.default_rng(deterministic_mix(base_seed, M3_SALT))` for all RNG use. No global state. No time-based seeds. |
| **M3-INV-2** | Marginal-match preserved to within `tol_marginal` (degree-sequence Wasserstein, density relative-error, spectral radius / N relative-error). |
| **M3-INV-3** | `K_null` is float64, symmetric, finite, shape `(T_HORIZON, N, N)`. |
| **M3-INV-4** | Same `(base_seed, null_seed, λ, N, substrate.id)` → bit-identical `K_null` and bit-identical `payload_sha256`. |
| **M3-INV-5** | Different `null_seed` (fixed `base_seed`) → different `K_null` for non-degenerate cells. |
| **M3-INV-6** | M3 verifier emits exactly one verdict literal from a locked Literal enum (analogous to `M2EligibilityStatus`). |
| **M3-INV-7** | Failure ⇒ fail-closed; no silent downgrade to M2 / M1 / no-op. |
| **M3-INV-8** | Locked governance unchanged (8-file sha256 pin, including D002C_CLAIM_LEDGER.yaml). |

## 5. Failure states

Locked enum candidates (to be finalised by the implementation PR):

* `ELIGIBLE_M3`
* `INELIGIBLE_M3_MARGINAL_MISMATCH`
* `INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC`
* `INELIGIBLE_M3_DEGENERATE_DISTANCE`
* `INELIGIBLE_M3_GENERATOR_DIVERGENT`
* `INDETERMINATE_M3_PROVENANCE_MISSING`

## 6. Negative controls (mandatory)

The M3 implementation PR MUST ship at least the following negative
controls; xfail with `reason=` is permitted only with a forward
pointer to the PR that resolves them:

1. **NC-M3-1**: a synthetic substrate whose marginals are
   IDENTICAL to its baseline (precursor null) must yield
   `INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC`. The matched generator
   cannot distinguish precursor from null.
2. **NC-M3-2**: a synthetic substrate whose marginals are
   IMPOSSIBLE to match (e.g. fractional degree sequence) must yield
   `INELIGIBLE_M3_GENERATOR_DIVERGENT`.
3. **NC-M3-3**: a substrate whose marginals match but whose K_null
   == K_p bit-identically must yield
   `INELIGIBLE_M3_DEGENERATE_DISTANCE`.
4. **NC-M3-4**: a substrate that raises during `realize()` must
   yield `INDETERMINATE_M3_PROVENANCE_MISSING`.

## 7. Forbidden interpretations

Even when an M3 implementation lands and emits `ELIGIBLE_M3` for
both currently-blocked substrates, that PR may NOT:

* declare D-002G scientific PASS (requires canonical sweep +
  Phase 0a/0b/0c verdicts + locked-governance pin pass);
* mutate `D002C_CLAIM_LEDGER.yaml`;
* close B2 (the percentile-CI limitation);
* authorise a canonical run (requires explicit authorisation
  artefact as per `D002G_P3_NULL_DOMAIN_CONTRACTS.md §7`).

## 8. Review checklist for the future M3 implementation PR

The PR that lands M3 MUST clear all of the following before merge:

- [ ] M3 enum literal added to `M2EligibilityStatus` (or a new
      `M3EligibilityStatus`) without removing existing literals.
- [ ] M3 verifier + realiser implemented with the locked salt
      (e.g. `M3_TOPOLOGY_CONDITIONED_SALT: Final[int] = 523` —
      distinct prime from 211/313/419/99).
- [ ] At least 30 tests: 6 verdict-ladder, 8 invariants (M3-INV-1
      through M3-INV-8), 4 negative controls, 8 adversarial traps,
      plus dispatch & salt-distinctness.
- [ ] `D002G_M3_IMPLEMENTATION_REPORT.md` shipped.
- [ ] Eligibility matrix updated to cover M3 column.
- [ ] BLOCKERS.md §B1.M3 subsection appended.
- [ ] Locked governance sha256 pin still PASS (this PR's anchor
      shas are byte-exact unchanged).
- [ ] No D-002G PASS claim string, no D-002C ledger touch, no
      canonical run artifact, no B2 closure claim.

## 9. Pre-registration lock

M3 pre-registration is locked at the merge commit of this PR
(`feat/x10r-d002g-p3-constant-payload-null-recovery`). Any
subsequent edit to this document constitutes a fresh M4
pre-registration. The locked salt for M3 RNG mixing is reserved
(523) but not yet implemented; reservation is recorded here so a
future PR cannot accidentally pick it for an unrelated mechanism.

### 9.1 Refinement scope contract (escape-hatch closure)

The phrase "implementation PR may refine implementation details" in §2
is bounded by the following explicit lists. These lists are part of the
M3 pre-registration lock; touching either list constitutes a fresh M4
pre-registration, not a patch to this M3.

**Allowed future refinement scope (implementation PR may decide):**
- concrete marginal-distance estimator implementation (e.g. specific
  Wasserstein quantile estimator, density relative-error formula,
  spectral-radius extractor) — provided the marginal set itself
  (degree sequence + block-label histogram + spectral radius / N +
  density) is unchanged;
- tolerance constants (`tol_marginal`, `tol_non_degenerate`,
  `tol_density`) — provided they are pre-declared in the M3
  implementation PR body BEFORE any canonical result is inspected and
  pinned in the implementation report's claim-boundary block;
- generator engineering details (sampling order, batching, vectorised
  paths) needed to satisfy the locked match-set deterministically.

**Forbidden future refinement scope (requires fresh M4 pre-registration):**
- replacing topology-conditioned independent realisation with another
  mechanism family (e.g. swapping to permutation, generative-model
  surrogate, or any non-marginal-matched null);
- adding post-hoc admissibility criteria after observing canonical
  outcomes (criteria adjustment-to-pass is the failure mode this
  pre-registration exists to prevent);
- removing or weakening any failure state enumerated in §5;
- removing or weakening any negative control enumerated in §6;
- changing the locked salt 523 to another value;
- authorising a canonical D-002G run from M3 eligibility alone
  (canonical run authorisation still requires the B1 ∧ B2 conjunction
  per `D002G_P3_NULL_DOMAIN_CONTRACTS.md §7`).

If the implementation PR finds a refinement need that falls outside the
Allowed list, the protocol-correct response is to open a fresh M4
pre-registration document, NOT to edit this one.
