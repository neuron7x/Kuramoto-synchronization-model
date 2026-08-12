# D-002G — Structural Closure Report

Anchor: PR #681 (M3 topology-conditioned independent realisation),
squash-merge commit `cced6e60f3b448878d51cb9848c990ab5133da28`.

This document is an append-only **negative-result retention artifact**.
It pins the structural impossibility of the locked 3-substrate
null-admissibility path into governance, so that a future M4 PR cannot
pretend to escape via cosmetic mechanism choice inside the current
D-002G pre-registration.

---

## 1. Executive verdict

> **D-002G STRUCTURAL CLOSURE.** The current locked 3-substrate
> null-admissibility path under PRs #677 / #679 / #680 / #681 is
> STRUCTURALLY BLOCKED. Canonical run remains BLOCKED. No scientific
> PASS claimed. No D-002C ledger mutation. Closure is scoped to the
> conjunction (D-002G prereg substrates × locked marginal set ×
> M1/M2/M3 mechanism families).

This is a **scoped** verdict. It does NOT claim D-002G globally
falsified; it does NOT claim `ricci_flow` invalid; it does NOT claim
universal invalidity of null mechanisms. The verdict is bounded by the
exact conjunction stated above and no further.

---

## 2. Evidence chain

The four prior PRs exhaust the M1/M2/M3 null-mechanism family against
the two M1-INELIGIBLE substrates (`block_structured`,
`temporal_coupling`) on the locked D-002G pre-registration grid:

| PR | merge sha | mechanism | result for blocked substrates | retained lesson |
|---|---|---|---|---|
| #677 | d3400c2e | M1 independent-seed | INELIGIBLE_M1_BIT_IDENTICAL | substrate discards seed by construction → independent-seed null collapses to bit-identity |
| #679 | 7b386ef3 | M2 edge-weight permutation | INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL | constant ΔK payload → edge-weight permutation is a no-op |
| #680 | 0f4433e0 | M2 node-payload + injection-sequence | INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED / INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE / CONTRACT_VIOLATION | node identity == topology; injection-sequence either degenerate or violates substrate contract |
| #681 | cced6e60 | M3 topology-conditioned independent realisation | INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC | locked marginals (degree + block + spectral/N + density) carry zero seed-dependent precursor signal |

Each row above is sha-pinned to a merged origin/main commit. Each
report (`D002G_P1_IMPLEMENTATION_REPORT.md`,
`D002G_P2_M2_IMPLEMENTATION_REPORT.md`,
`D002G_P3_IMPLEMENTATION_REPORT.md`,
`D002G_M3_IMPLEMENTATION_REPORT.md`) is retained read-only in
`docs/governance/`. This closure report does not edit them.

---

## 3. Bottom-turtle fact

The structural cause of every verdict in §2 is one line of substrate
code:

```
research/systemic_risk/d002c_substrates.py:
    _ = seed  # block substrate is fully deterministic in N, lambda_
```

Located at `research/systemic_risk/d002c_substrates.py:401`, inside
`BlockStructuredSubstrate.realize()`. This line is not a bug — it is
the locked **substrate API contract** for `block_structured` under the
D-002G pre-registration. It encodes the deliberate design choice that
the block substrate has *no stochastic content* in its realisation.

Downstream consequences, by code:

- `BlockStructuredSubstrate.realize()` line 401 explicitly discards
  the `seed` parameter via the `_ = seed` idiom.
- `TemporalKtSubstrate.realize()` (line 481-483) constructs its
  baseline by calling `BlockStructuredSubstrate(...).realize(N=N,
  lambda_=0.0, seed=seed)` — inheriting the seed-discard via
  delegation. The `temporal_coupling` substrate carries the same
  structural property as the block substrate plus a deterministic
  sinusoidal envelope.
- The sinusoidal envelope (line 485-486) is deterministic in
  `period_quarters` + `amplitude` — no seed.
- The precursor lift (line 493-497) is deterministic in `λ` and `K_c`
  — no seed.

**Result: for both substrates, no quantity in `K_p` depends on
`base_seed`.** The locked marginal set used by the M3 verifier
(degree sequence, block-label histogram, spectral radius / N, density)
is therefore seed-INVARIANT by substrate construction. The M3
admissibility criterion 3 (`Identifiable from precursor`) requires
that different precursor seeds yield different marginals with
probability ≥ 0.5 over 100 paired seeds. A seed-invariant marginal
set produces 0 / 99 distinct adjacent-seed pairs against the required
≥ 50 / 99. The criterion fails by construction, not by parameter
choice or numerical accident. **The fact is encoded in the substrate
class itself.**

The same line is the root cause of every prior verdict in §2:

- M1 independent-seed (PR #677): null is bit-identical to precursor
  because both share the seed-invariant K(N, λ).
- M2 edge-weight permutation (PR #679): the precursor ΔK contains a
  single constant payload value driven by `0.25 · λ · K_c`, with no
  seed-dependent perturbation; permuting a constant multiset is a
  no-op.
- M2 node-payload (PR #680): the block label IS the node label space
  — there is no decoupled "node identity" to permute.
- M2 injection-sequence (PR #680): injection events are either the
  precursor itself (and so the sequence IS the causal hypothesis) or
  the sequence length is below the non-degeneracy threshold.
- M3 topology-conditioned (PR #681): explained above — seed-invariant
  marginals.

---

## 4. Formal conclusion

B1 (substrate eligibility) cannot be closed under the current D-002G
locked grid without **one** of the following:

- **A. Scope narrowing** — fresh pre-registration restricting the
  canonical grid to `ricci_flow` only. The M1 / M2 (edge-weight) / M3
  surface already lands ELIGIBLE for `ricci_flow`; a scope-narrowed
  prereg would acknowledge the two blocked substrates as
  out-of-scope.
- **B. Substrate redesign** — fresh pre-registration replacing the
  `block_structured` and `temporal_coupling` substrate specifications
  with seed-dependent variants. This is a substrate-API surgery, not
  a null-mechanism PR.
- **C. Closure as negative artifact** — retain D-002G as
  structurally-blocked and do NOT attempt B1 closure. The negative
  result IS the scientific result; it is preserved by this artifact.

Each path requires a **FRESH** pre-registration document (D-002H or
later). Editing the D-002G pre-registration in any of these paths is
forbidden by its own anchor lock, by the M3 pre-reg §9.1 forbidden
refinement scope, and by the cross-PR test
`tests/systemic_risk/test_d002g_m3_no_promotion.py::test_m3_p3_m3_prereg_unchanged`.

This closure report does **not** make the decision between A / B / C.
The decision is reserved for the next pre-registration cycle.

---

## 5. Forbidden interpretations

The following readings of this artifact are explicitly disallowed:

- ❌ "This PR proves D-002G scientifically falsehood." It proves the
  locked path is structurally blocked for the conjunction described;
  the scientific question is not adjudicated.
- ❌ "This PR proves ricci_flow invalid." `ricci_flow` is M1-eligible
  and M3-eligible; the closure scope excludes it.
- ❌ "This PR proves all null mechanisms invalid." The M1/M2/M3
  family is exhausted for THESE substrates; other substrate designs
  are untested.
- ❌ "This PR authorises canonical run." Canonical run remains
  BLOCKED.
- ❌ "This PR updates D002C_CLAIM_LEDGER.yaml." It does NOT. The
  ledger sha256 is byte-exact preserved.
- ❌ "This PR permits post-hoc M4 inside D-002G." M4 mechanism inside
  the locked grid is structurally meaningless; M4 requires fresh
  pre-registration.

---

## 6. Next legal paths

Three legal paths are available; each requires a fresh
pre-registration document.

- **A — `D002H_SCOPE_NARROWING`.** Fresh pre-registration restricting
  the canonical D-002G grid to `ricci_flow` only.
- **B — `D002H_SUBSTRATE_REDESIGN`.** Fresh pre-registration
  replacing `block_structured` + `temporal_coupling` specs with
  seed-dependent variants.
- **C — `D002G_NEGATIVE_ARTIFACT_RETENTION`.** Retain D-002G as
  structurally-blocked; do NOT attempt B1 closure.

> Decision among A/B/C is deferred to the next pre-registration
> cycle. This artifact does NOT make the decision.

---

## 7. Decision recommendation

Recommendation (non-binding):

> Recommendation (non-binding): merge this structural closure artifact
> FIRST. Then open a fresh D-002H pre-registration PR that explicitly
> declares which path among A/B/C is chosen. Do NOT amend D-002G
> post-hoc with an "M4 inside D-002G" — that conflates a fresh
> pre-registration with a patch.

The asymmetry between "fresh pre-reg PR" and "post-hoc patch" is the
core of the pre-registration discipline; it is what gives the
scoped-closure verdict any value at all. Collapsing the asymmetry
would retroactively invalidate every prior D-002G verdict the
discipline produced.

---

## Appendix — Allowed claim (verbatim)

The only claim this artifact makes is the following:

> The current D-002G locked substrate/null-admissibility path is
> STRUCTURALLY BLOCKED for the canonical 3-substrate grid because
> `block_structured` and `temporal_coupling` do not carry
> precursor-specific stochastic content required by M1/M2/M3
> admissible null mechanisms. Closure is SCOPED to the conjunction
> (D-002G prereg substrates × locked marginal set × M1/M2/M3
> mechanism families). It does NOT prove D-002G globally falsified;
> it does NOT prove ricci_flow invalid; it does NOT prove universal
> invalidity of null mechanisms.

Anything beyond this allowed claim is out of scope for this PR and
forbidden by §5.
