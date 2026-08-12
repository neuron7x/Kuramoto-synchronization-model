<!-- no-bio-claim -->
# PNCC CANONS

Canonical reference for the GeoSync **Physics-Native Cognitive Kernel
(PNCC)**. Every PNCC module, doc, and test cites this file. PNCC is
**experimental / opt-in** and makes **no claim of biological
optimization, no medical language, and no causal cognitive-performance
assertion** — see §INV-NO-BIO-CLAIM and the disclaimer template at the
end of this document.

> **Status:** experimental, opt-in. Single-arm only — no crossover, no
> Bayes-factor scoring yet. Persistence is in-memory; serialize via
> `EvidenceRegistry.to_json` for the durable 90-day evidence-ledger
> workflow described in §Workflow.

---

## 1. The 7 CANONS

These canons govern *every* PNCC artefact. They are non-negotiable.

1. **Physics-first, not biology-first.** PNCC primitives are
   thermodynamic / information-theoretic (Landauer bound, reversible
   computation, free energy). Biological analogies, if any, are
   descriptive only and never load-bearing.
2. **No claim without evidence.** No cognitive-performance,
   productivity, or latency claim is valid without a registered
   `EvidenceClaim` (baseline, intervention, n ≥ 30 per arm, 95% CI,
   stat test, hypothesis ID).
3. **Pre-registration is mandatory.** Hypotheses are registered
   *before* data collection. The five PNCC hypotheses below are
   pre-registered in `tacl.evidence_ledger.HypothesisId`.
4. **Negative findings are first-class.** A registered claim with a
   negative effect size or wide CI is a valid scientific result. The
   ledger MUST persist refuted hypotheses.
5. **Fail-closed validation.** Missing samples (n < 30), non-finite
   numerics, inverted CIs, or out-of-range p-values reject the claim.
6. **Immutability + content addressing.** `EvidenceClaim` is a frozen
   dataclass. `LedgerEntry.claim_hash` is SHA-256 over canonical
   JSON. Tampering is detected on `from_json`.
7. **CI-enforced contract.** `INV-NO-BIO-CLAIM` is enforced both at
   runtime (`scan_source_for_bio_claims`) and as a CI lint over
   `core/`, `tacl/`, `runtime/`, `geosync/`.

---

## 2. The 5 HYPOTHESES (PRE-REGISTERED)

Pre-registered in `tacl.evidence_ledger.HypothesisId`. Each requires a
baseline ≥ 30 sessions, intervention ≥ 30 sessions, paired or
two-sample stat test, 95% CI, and effect size in the registered
`EvidenceClaim`.

| ID    | Name              | Outcome variable                                  | Direction tested |
|-------|-------------------|---------------------------------------------------|------------------|
| HYP-1 | DECISION_LATENCY  | wall-clock seconds from prompt to validated commit | reduction        |
| HYP-2 | ERROR_RECOVERY    | mean recovery time from a CI red → green          | reduction        |
| HYP-3 | CNS_SCHEDULING    | tokens-per-correct-action under the CNS proxy     | reduction        |
| HYP-4 | COMPUTE_COST      | dollar-cost per merged PR (model + infra)         | reduction        |
| HYP-5 | COMBINED_LOOP     | composite of HYP-1..HYP-4 in a single A/B loop    | reduction        |

> Hypothesis IDs are FROZEN. Adding a new hypothesis requires a new
> `HypothesisId` enum value PLUS a new row here PLUS a corresponding
> entry in `physics_contracts/`. Both layers must be updated atomically
> (per the GeoSync two-layer physics-contracts protocol).

---

## 3. The 5 INVARIANTS

Each invariant has a statement, a falsification axis, and a test
pointer. P0 = blocking; P1 = high-priority; P2 = nice-to-have.

> **Historical note.** A sixth invariant tied to the proposed PNCC-B
> initializer was struck during 2026-04-25 citation cleanup: the
> empirical anchor we had on file was an unverified arXiv ID, and the
> module was never built. Any future proposal for that primitive must
> arrive with a verifiable peer-reviewed reference and re-enter via a
> new pre-registered hypothesis row.

### INV-LANDAUER-PROXY (P0, universal)

**Statement.** For any pair of actions with identical
(token, latency, entropy) components, the irreversible-action proxy
cost dominates the reversible-alternative cost: C_irr ≥ C_rev,
with strict > whenever irreversibility_score > 0
(Landauer 1961, *IBM J. Res. Dev.* 5, 183).
**Falsification axis.** Any (irrev, rev) pair with identical
(token, latency, entropy) components where C_irr < C_rev.
**Test pointer.** `tests/unit/physics/test_thermodynamic_budget.py`
(11 functions, 1000-pair sweep).
**Source.** `core/physics/thermodynamic_budget.py` (PNCC-A, merged: PR #378).
**Registry.** `.claude/physics/INVARIANTS.yaml::pncc.landauer_proxy`,
`physics_contracts/catalog.yaml::pncc.landauer_proxy_dominance`
(Wave 1.5, PR #383).

### INV-REVERSIBLE-GATE (P0, universal)

**Statement.** Every reversible-gate primitive has zero net
information erasure on its forward+inverse composition; its energy
ledger is bit-balanced (Bennett 1973, *IBM J. Res. Dev.* 17, 525).
**Falsification axis.** A reversible composition with non-zero net
erasure energy at p < 0.01 over n ≥ 30 invocations.
**Test pointer.** `core/physics/reversible_gate.py` (PNCC-C, merged:
PR #380).

### INV-FREE-ENERGY (P0, monotonic)

**Statement.** Under active inference the controller's free energy
F = U − T·S is non-increasing; components U, T, S are individually
non-negative (matches GeoSync `INV-FE1`/`INV-FE2`).
**Falsification axis.** Trajectory with monotone-violation count > 0
on filtered trace.
**Test pointer.** `tacl/energy_model.py` (existing).

### INV-CNS-SAFETY (P0, conditional)

**Statement.** The CNS proxy adapter must refuse to dispatch any
action whose composite distress T ≥ entry threshold (matches
GeoSync `INV-CB8` cryptobiosis safety).
**Falsification axis.** A ledgered session with T ≥ entry that
nevertheless dispatched.
**Test pointer.** Inherits from GeoSync `INV-CB8` cryptobiosis safety
test suite; a dedicated CNS-proxy adapter is not yet implemented and
does not block the canon — the cryptobiosis layer already enforces
the underlying T ≥ entry refusal.

### INV-NO-BIO-CLAIM (P0, universal)

**Statement.** Any module emitting cognitive-performance language
must have an associated `EvidenceClaim` registered for the relevant
hypothesis OR a disclaimer phrase from `allowed_disclaimer_phrases`.
**Falsification axis.** AST-grep over `core/`, `tacl/`, `runtime/`,
`geosync/` returns ≥ 1 violation that is NOT in a test file and NOT
in an explicit disclaimer.
**Test pointer.** `tests/tacl/test_evidence_ledger.py
::test_self_scan_finds_zero_naked_violations_in_pncc_modules`.

> **Refinement note.** The medical-claim heuristic
> `\b(diagnose|treat)\s+\w+` from the original spec was tightened to
> require a medical/cognitive object (`disease|condition|disorder|
> illness|...|memory|focus|attention|cognition|the brain|patient|
> symptom`). The bare form had a high false-positive rate on generic
> English (e.g. "treat as inclusive", "treat each edge"). Documented
> here per the GeoSync rule that physics-contract relaxations must
> be recorded in the contract file, not in commit messages.

---

## 4. No-bio-claim disclaimer template

PNCC docs that mention cognition / focus / productivity / brain MUST
include this paragraph (or an equivalent that contains at least one
phrase from `allowed_disclaimer_phrases` per scoped paragraph):

> **No-bio-claim disclaimer.** This document makes no claim of a
> biological optimization, no medical language, and no causal
> cognitive-performance assertion. Numbers reported are
> correlation-only, derived from ledgered `EvidenceClaim` records
> (baseline, intervention, n ≥ 30, 95% CI, stat test). Negative
> effect sizes (HYP rejection) are first-class results.

The phrases `make no claim`, `is not a` (medical claim), `no causal`,
`correlation-only`, `no-bio-claim`, `does NOT`, and `no medical` are
the canonical disclaimer markers.

---

## 5. Source anchors

Only foundational, peer-reviewed, decades-stable references are kept
here. A 2026-04-25 audit removed five unverified 2025/2026
references that could not be located in any indexable venue;
engineering claims that previously rested on those references have
been restructured to depend only on the foundational anchors below.

- **Landauer's principle.** R. Landauer, *IBM J. Res. Dev.* 5 (1961)
  183 — minimum energy of irreversible bit erasure ≥ k·T·ln 2.
- **Reversible computing.** C. H. Bennett, *IBM J. Res. Dev.* 17
  (1973) 525 ("Logical reversibility of computation"); Bennett,
  *Int. J. Theor. Phys.* 21 (1982) 905 (thermodynamics of
  computation).
- **Free energy principle.** K. Friston, *Nat. Rev. Neurosci.* 11
  (2010) 127 ("The free-energy principle: a unified brain theory?")
  — variational free energy minimization in active inference.
- **Distributionally Robust Optimization.** Generic theoretical
  reference for the DR-FREE-style worst-case formulation; no
  specific 2025/2026 paper is asserted here.
- **Pre-registration practice.** COS Open Science Framework
  guidelines; Lakens (2013) on effect sizes; APA 7 §3.7 on CI
  reporting.

---

## 6. Workflow — 90-day evidence ledger

1. **Pre-register** the hypothesis in `HypothesisId` (already FROZEN
   for the five PNCC hypotheses; new hypotheses require a CANONS.md
   update + matching enum value).
2. **Collect baseline** for ≥ 30 sessions. Persist raw timing/cost
   metrics with session IDs.
3. **Apply intervention** for ≥ 30 sessions on the same operator
   pool, same task distribution.
4. **Run stat test** appropriate to the data shape (two-sample t,
   Wilcoxon, permutation). Record `test_statistic`, `p_value`, `df`.
5. **Compute effect size + 95% CI** (Cohen's d or analogue).
6. **Register the claim** via
   `EvidenceRegistry.register(EvidenceClaim(...))`. The registry
   validates fail-closed and assigns a content-addressable hash.
7. **Query downstream gates** by `HypothesisId` to drive any decision
   that depends on the claim. Queries return tuples — never mutate.
8. **Persist** the registry as JSON for the 90-day horizon.
9. **Re-evaluate** at horizon expiry: re-register a fresh claim or
   archive. Existing hashed entries are immutable.

---

## 7. Two-layer physics-contracts protocol

GeoSync maintains two parallel physics-contract layers:

- `.claude/physics/` — assistant-facing spec (this CANONS.md)
- `physics_contracts/` — runtime-enforced invariants

Any change to PNCC canons / hypotheses / invariants MUST update both
layers atomically in the same commit. CANONS.md is the
assistant-facing entry point; the runtime layer is consumed by
`tacl.evidence_ledger.scan_source_for_bio_claims` and the test suite.

---

## 8. Module cross-reference

| Concept                | Module / function                                                  |
|------------------------|--------------------------------------------------------------------|
| Hypothesis enum        | `tacl.evidence_ledger.HypothesisId`                                |
| Evidence claim         | `tacl.evidence_ledger.EvidenceClaim`                               |
| Statistical test       | `tacl.evidence_ledger.StatTest`                                    |
| Ledger entry           | `tacl.evidence_ledger.LedgerEntry`                                 |
| Registry               | `tacl.evidence_ledger.EvidenceRegistry`                            |
| Hashing                | `tacl.evidence_ledger.claim_hash`, `claim_canonical_json`          |
| Validation             | `tacl.evidence_ledger.validate_claim`                              |
| AST-grep guard         | `tacl.evidence_ledger.scan_source_for_bio_claims`                  |
| Disclaimer phrases     | `tacl.evidence_ledger.DEFAULT_DISCLAIMER_PHRASES`                  |
| Forbidden patterns     | `tacl.evidence_ledger.DEFAULT_FORBIDDEN_PATTERNS`                  |
