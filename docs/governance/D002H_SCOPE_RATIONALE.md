# D-002H Scope Rationale

> Pre-registration anchor: `docs/governance/D002H_PREREGISTRATION.yaml`.
> Lineage: fresh pre-registration after D-002G structural closure
> (PR #682 merge `8cf5364a3f3b605d8b134bccbfe5170098e0e197`).
>
> This document is the read-only rationale that pins WHY D-002H exists,
> WHY D-002G cannot be amended, WHY ricci_flow is the only admissible
> substrate, and WHAT claims become possible vs forbidden under the
> narrowed scope. It is an append-only artifact of the D-002H lineage;
> any post-merge edit constitutes a fresh D-002J pre-registration, NOT
> a patch.

---

## 1. Why D-002H exists

D-002G closed structurally per `docs/governance/D002G_STRUCTURAL_CLOSURE_REPORT.md`
(PR #682 merge `8cf5364a3f3b605d8b134bccbfe5170098e0e197`). The closure
verdict ruled the M1 / M2 / M3 null-mechanism family INELIGIBLE for two
of three pre-registered substrates (`block_structured`,
`temporal_coupling`) by substrate-design constraint. The original
research question — "does a null-audit work on a single physical
network model under the locked pre-registration discipline?" — remains
scientifically valuable on `ricci_flow` alone, where the M1 and M3
verifiers landed ELIGIBLE across the canonical N grid.

D-002H opens a FRESH pre-registered lineage that scopes the canonical
run to `ricci_flow` only. The closure-before-restart canon dictates
that the failed D-002G lineage stays sha-pinned as a negative artifact
in PR #682; D-002H does not amend it, does not rescue it, and does not
inherit its allowed-claims surface beyond the explicit exclusion
acknowledgement.

---

## 2. Why D-002G cannot be amended

The D-002G pre-registration is sha-locked at its own merge commit, per
`D002G_PREREGISTRATION.yaml §8` (forbidden post-hoc changes) and the
cross-PR test
`tests/systemic_risk/test_d002g_m3_no_promotion.py::test_m3_p3_m3_prereg_unchanged`.
Any edit to the D-002G prereg, or any "M4 inside D-002G" attempt,
would:

- violate the D-002G own anchor lock (yaml `forbidden_to_post_hoc_change`
  list, including the prereg file itself, the null mechanism block,
  and the phase_0_verification block);
- violate the M3 pre-registration §9.1 forbidden-refinement-scope
  clause, which explicitly prohibits "authorising a canonical D-002G
  run from M3 eligibility alone";
- violate the closure-before-restart discipline established by
  `D002G_STRUCTURAL_CLOSURE_REPORT.md §4` (each next legal path
  requires a FRESH pre-registration document — D-002H or later).

The four negative-result PRs (#677, #679, #680, #681) plus the
structural closure artifact (#682) form an append-only canonical
record. D-002H does not modify them.

---

## 3. Why ricci_flow remains admissible

The `ricci_flow` substrate (`RicciFlowSubstrate.realize()` in
`research/systemic_risk/d002c_substrates.py`) does NOT discard its seed.
The D-002G evidence chain documents the following positive eligibility
verdicts:

- **M1 eligibility:** ELIGIBLE_M1 across the canonical N grid
  ({50, 100, 200}) at λ=0.4, per the P1 ledger and the
  `D002G_M3_ELIGIBILITY_MATRIX.md` summary table.
- **M3 eligibility:** ELIGIBLE_M3 across the canonical N grid at
  λ=0.4, `null_seed=12345`, salt 523, per
  `docs/governance/D002G_M3_ELIGIBILITY_MATRIX.md` rows 1-3 (substrate
  `ricci_flow`, N ∈ {50, 100, 200}).

These verdicts are inherited as evidence into D-002H scope; they are
NOT re-claimed under D-002H. D-002H requires re-verification under its
own Gate B before any downstream canonical run is opened (see
`D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md §B`).

M2 edge-weight on `ricci_flow` was also ELIGIBLE per
`D002G_M3_ELIGIBILITY_MATRIX.md` — but D-002H restricts the allowed
null mechanism set to {M1_INDEPENDENT_SEED, M3_TOPOLOGY_CONDITIONED}
to keep the contract minimal; M2 sub-domains are retained as
historical evidence only and are not part of the canonical D-002H
mechanism allowlist.

---

## 4. Why block_structured and temporal_coupling are excluded

The closure report §3 quotes the bottom-turtle code fact verbatim:

```
research/systemic_risk/d002c_substrates.py:
    _ = seed  # block substrate is fully deterministic in N, lambda_
```

Located at `research/systemic_risk/d002c_substrates.py:401`, inside
`BlockStructuredSubstrate.realize()`. The line is the locked substrate
API contract — the block substrate has no stochastic content in its
realisation.

`TemporalKtSubstrate.realize()` (lines 481-483) inherits the
seed-discard via delegation:

```python
base = BlockStructuredSubstrate(block_fractions=BLOCK_FRACTIONS).realize(
    N=N, lambda_=0.0, seed=seed
)
```

The downstream sinusoidal envelope (lines 485-486) is deterministic in
`period_quarters` + `amplitude` — no seed. The precursor lift
(lines 493-497) is deterministic in `λ` and `K_c` — no seed.

Consequence: for both substrates, NO quantity in `K_p` depends on
`base_seed`. The locked marginal set used by the M3 verifier (degree
sequence, block-label histogram, spectral radius / N, density) is
therefore seed-invariant by substrate construction. NO null mechanism
conditioned on the locked marginal set can satisfy
`precursor-specificity criterion 3` (≥ 50 / 99 adjacent-seed pairs
distinct) for these substrates.

D-002H therefore excludes both substrates EXPLICITLY in
`D002H_PREREGISTRATION.yaml::substrate_scope.excluded`. The exclusion
is structural, not a post-hoc parameter narrowing.

---

## 5. What claims become impossible

The narrowed scope makes the following claims STRUCTURALLY IMPOSSIBLE
under D-002H, irrespective of canonical-run outcome:

- **Cross-substrate robustness.** A 1-substrate result cannot
  triangulate across substrate types.
- **General topology robustness.** Ricci-flow topologies are a
  specific construction; no claim of general-graph robustness can be
  made.
- **Mechanism generalisation beyond ricci_flow.** Even within the
  allowed {M1, M3} pair, generalisation to substrates outside the
  included list is forbidden.
- **Any aggregated claim across substrate types.** The aggregate
  estimator denominator drops from 3 substrates to 1; statistical
  power loss is √3 ≈ 1.7× standard-error reduction for any aggregated
  claim that would have been possible on the original D-002G grid.

These claim-losses are accepted COSTS of the scope-narrowing path. The
alternative paths (substrate redesign, negative-artifact retention)
were considered by the closure report §6 and remain available as
separate future pre-registration cycles; D-002H selects the
scope-narrowing path explicitly.

---

## 6. What claims remain possible

Within the narrowed scope, the following claims become tractable when
authorised by a separate downstream artifact passing all 7 gates A..G:

- **Within-`ricci_flow` null admissibility under M1 and M3.**
  Re-verified eligibility on the D-002H canonical grid.
- **Phase-0 verification on `ricci_flow`** (per `D002G_ACCEPTANCE_RULES.md §4`
  bit-identity-broken / H0-preserved / permutation-discriminability-non-trivial),
  applied only to the ricci_flow substrate row.
- **Canonical sweep on the narrowed grid** (3 N × 6 λ × 20 seeds × 16
  bootstrap × 1 substrate = 18 cells × ensemble) — gated on Gate F
  authorisation artifact existing on disk.
- **Synthetic GATE6 certification scoped to `ricci_flow`** when
  authorised — analogous to D-002G `acceptance.primary_certification_rule.tier_if_pass`
  but explicitly scope-labelled `SYNTHETIC_GATE6_CERTIFIED_D002H_RICCI_ONLY`
  in the downstream run authorisation artifact (NOT in this prereg).

None of these claims is asserted in THIS PR. THIS PR locks the prereg
and the gates that would gate them.

---

## 7. Why this is not post-hoc rescue

The pre-registration discipline distinguishes "fresh study" from
"post-hoc parameter tuning of a failed study". D-002H meets the
fresh-study test on each of the following axes:

- **Distinct study identifier.** `study_id: D-002H`, distinct from
  `D-002G` and `D-002C`.
- **Distinct lineage label.** `lineage_type: fresh_preregistration`,
  with `parent_closure: D-002G_STRUCTURAL_CLOSURE`.
- **Distinct research question.** "Does null-audit work on
  `ricci_flow` only?" is strictly narrower than the original
  3-substrate question; the narrowing is documented IN THIS PR
  (not inferred from canonical outcomes that have not yet happened).
- **Distinct allowed-claims set.** `allowed_claims` explicitly omits
  cross-substrate generalisation; `forbidden_claims` enumerates
  exactly the claims that the narrowing forbids.
- **Distinct canonical grid.** 18 cells (1 substrate × 3 N × 6 λ)
  vs D-002G's 54 cells (3 × 3 × 6).
- **No mutation of prior pre-registration.** D-002G prereg, D-002G
  P3/M3 prereg, D-002C prereg, and D-002C claim ledger are all
  byte-exact unchanged at this PR's merge commit.

Fresh pre-registration with EXPLICIT scope-narrow rationale BEFORE any
canonical D-002H result is observed is the canonical anti-rescue
discipline; it is exactly the asymmetry that gives the prior negative
verdicts their scientific weight.

---

## 8. Boundary against cross-substrate generalisation

Any future paper, README, slide deck, or claim that builds on D-002H
canonical-run output MUST observe the following boundary:

> Results from a D-002H canonical run are valid only within the
> `ricci_flow` substrate boundary. Generalisation to `block_structured`,
> `temporal_coupling`, or arbitrary graph topologies is NOT supported
> by D-002H.

Reviewers comparing a D-002H result to multi-substrate ambitions (e.g.
the original D-002C 3-substrate framing, or any "general systemic
risk" framing) MUST reject the generalisation. The boundary is
restated verbatim in `D002H_CLAIM_BOUNDARY.md` and is enforced by the
test `tests/systemic_risk/test_d002h_preregistration.py::test_d002h_claim_boundary_verbatim_present`.
