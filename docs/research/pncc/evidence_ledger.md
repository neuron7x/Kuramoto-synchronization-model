<!-- no-bio-claim -->
# PNCC Evidence Ledger

> **Status:** experimental / opt-in. Companion module to
> [`docs/research/pncc/CANONS.md`](./CANONS.md).
>
> **No-bio-claim disclaimer.** This document makes no claim of a
> biological optimization, no medical language, and no causal
> cognitive-performance assertion. The ledger records *measurements*;
> it is not a medical or diagnostic instrument. Negative effect sizes
> (HYP rejection) are first-class results — recording rejection is
> the principal use-case (correlation-only).

---

## What this module does

`tacl.evidence_ledger` is the contract-enforcement layer of the
GeoSync Physics-Native Cognitive Kernel (PNCC). It enforces the rule
that **no cognitive-performance claim is valid without measured
baseline, intervention, control, and 95% confidence interval.**

It provides:

- a frozen `EvidenceClaim` schema (baseline / intervention means,
  stds, n, effect size, CI95, statistical test, hypothesis ID,
  pre-registration flag);
- an append-only `EvidenceRegistry` with content-addressable SHA-256
  hashing;
- `validate_claim(...)` — fail-closed checks (n ≥ 30 per arm, finite
  numerics, monotone CI, p-value ∈ [0, 1]);
- `scan_source_for_bio_claims(...)` — the AST-grep guard that
  enforces `INV-NO-BIO-CLAIM` over `core/`, `tacl/`, `runtime/`,
  `geosync/` at runtime AND as a CI lint;
- five PRE-REGISTERED hypotheses (`HypothesisId.HYP_1..HYP_5`).

---

## The 7 CANONS (reference)

See [`CANONS.md`](./CANONS.md) §1 for the full text. Summary:

1. Physics-first, not biology-first.
2. No claim without evidence.
3. Pre-registration is mandatory.
4. Negative findings are first-class.
5. Fail-closed validation.
6. Immutability + content addressing.
7. CI-enforced contract.

---

## The 5 HYPOTHESES (PRE-REGISTERED)

| ID    | Name              | Outcome variable                                  | Direction tested |
|-------|-------------------|---------------------------------------------------|------------------|
| HYP-1 | DECISION_LATENCY  | wall-clock seconds from prompt to validated commit | reduction        |
| HYP-2 | ERROR_RECOVERY    | mean recovery time from a CI red → green          | reduction        |
| HYP-3 | CNS_SCHEDULING    | tokens-per-correct-action under the CNS proxy     | reduction        |
| HYP-4 | COMPUTE_COST      | dollar-cost per merged PR (model + infra)         | reduction        |
| HYP-5 | COMBINED_LOOP     | composite of HYP-1..HYP-4 in a single A/B loop    | reduction        |

These IDs are FROZEN. See [`CANONS.md`](./CANONS.md) §2.

---

## Invariant: INV-NO-BIO-CLAIM (P0, universal)

> Any module emitting cognitive-performance language must have an
> associated `EvidenceClaim` registered for the relevant hypothesis
> OR a disclaimer phrase from `allowed_disclaimer_phrases`.

**Falsification axis.** AST-grep over `core/`, `tacl/`, `runtime/`,
`geosync/` returns ≥ 1 violation that is NOT in a test file and NOT
in an explicit disclaimer.

**Test pointer.** `tests/tacl/test_evidence_ledger.py
::test_self_scan_finds_zero_naked_violations_in_pncc_modules`.

The guard runs both at runtime (`scan_source_for_bio_claims`) and as
a CI lint. Test files (under `/tests/` or `/test/`, or named
`test_*.py` / `*_test.py`) are skipped because they assert the bans.
Lines within a 5-line window of an `EvidenceClaim` / `HypothesisId` /
`HYP-N` reference are skipped because they are claim-anchored.

---

## 90-day evidence-ledger workflow

1. **Pre-register.** Confirm the hypothesis exists in
   `HypothesisId`. The five PNCC hypotheses are FROZEN; adding a new
   one requires updating `CANONS.md` and the enum atomically.
2. **Collect baseline** for ≥ 30 sessions. Persist raw timing / cost
   per session.
3. **Apply intervention** for ≥ 30 sessions on the same operator pool
   and task distribution.
4. **Run a stat test** appropriate to the data shape — two-sample
   t-test, Wilcoxon signed-rank, or permutation. Record
   `test_statistic`, `p_value`, optional `df`.
5. **Compute effect size + 95% CI** (Cohen's d or analogue).
6. **Register the claim:**
   ```python
   from tacl.evidence_ledger import (
       EvidenceClaim, EvidenceRegistry, HypothesisId, StatTest,
   )

   registry = EvidenceRegistry(horizon_days=90)
   claim = EvidenceClaim(
       hypothesis=HypothesisId.HYP_1_DECISION_LATENCY,
       baseline_mean=412.7, baseline_std=58.3, baseline_n=64,
       intervention_mean=388.1, intervention_std=55.0, intervention_n=64,
       effect_size=-0.43, ci_95_low=-0.78, ci_95_high=-0.08,
       stat_test=StatTest("two-sample t-test", -2.41, 0.018, 126.0),
       registered_at_ns=1_700_000_000_000_000_000,
       pre_registered=True,
       notes="A/B run 2026-04-23 → 2026-04-24",
   )
   entry = registry.register(claim)  # returns LedgerEntry with sha256 hash
   ```
7. **Query downstream gates** by hypothesis:
   ```python
   for entry in registry.query(HypothesisId.HYP_1_DECISION_LATENCY):
       print(entry.claim_hash, entry.claim.effect_size)
   ```
8. **Persist** via `registry.to_json()` for the 90-day horizon.
9. **Re-evaluate at horizon expiry:** register a fresh claim or
   archive. Existing entries are immutable.

A failed claim — i.e. effect_size > 0 (regression) or CI95 spanning
zero — is a valid registered finding under canon 4 (negative findings
are first-class).

---

## Validation rules (fail-closed)

`validate_claim(claim, *, min_n=30)` returns
`(is_valid, reason_if_invalid)`:

- `baseline_n >= min_n` and `intervention_n >= min_n`;
- every numeric field is finite (no NaN / ±Inf);
- `ci_95_low <= ci_95_high`;
- `p_value` in `[0.0, 1.0]`;
- `baseline_std` and `intervention_std` non-negative;
- non-zero std on both arms UNLESS `effect_size == 0` exactly (a
  degenerate constant arm is only meaningful with a zero effect).

`EvidenceRegistry.register` raises `ValueError` on rejection.
`EvidenceRegistry.from_json` re-validates the SHA-256 hash on every
entry — tampered ledgers fail to load.

---

## AST-grep guard

The guard is exposed as
`tacl.evidence_ledger.scan_source_for_bio_claims(paths, ...)` and
ships with two default tuples:

- `DEFAULT_FORBIDDEN_PATTERNS` — seven regex patterns. <!-- no-bio-claim --> The doc make no claim of any of the following; they are listed as the literal strings the guard will flag: "improve memory", "boost focus", "enhance cognition", "optimize the brain", `\d+x productivity`, `+ N–M % productivity`, plus a tightened medical-claim heuristic for `diagnose / treat`-style phrasings. <!-- no-bio-claim -->
- `DEFAULT_DISCLAIMER_PHRASES` — nine phrases that mark explicit
  denials (`does NOT`, `make no claim`, `is NOT a`, `is not a`,
  `no claim of`, `no causal`, `correlation-only`, `no-bio-claim`,
  `no medical`).

Skip rules (in order):

1. Path is a test file → skip.
2. Line contains a disclaimer phrase → skip.
3. Line is within a 5-line window of an EvidenceClaim / HypothesisId
   / `HYP-N` reference → skip (claim-anchored).
4. Otherwise, every regex match becomes a `BioClaimViolation`.

> **Refinement note.** The original spec used the broad pattern
> `\b(diagnose|treat)\s+\w+`. We tightened the object set to
> medical/cognitive nouns to make the lint usable as a CI gate
> without flagging generic English ("treat as inclusive"). See
> [`CANONS.md`](./CANONS.md) §INV-NO-BIO-CLAIM for the full
> rationale.

---

## Known limitations

- **In-memory only.** Persistence is via `to_json` / `from_json`.
  No database backend is provided.
- **Single-arm only.** No crossover, no within-subject design, no
  Bayes-factor scoring yet.
- **Hash assumes canonical JSON.** Numeric fields are serialized as
  Python floats; reconstruction roundtrips byte-identically.
- **Allow-listed disclaimers are textual.** A pathological author
  could embed a disclaimer phrase to silence the guard. Reviewers
  must read the disclaimer in context — the guard is a lint, not a
  proof of honesty.
- **CI lint scope.** The default scan covers `core/`, `tacl/`,
  `runtime/`, `geosync/`. Other trees (e.g. `docs/`, `examples/`)
  are not scanned by default; extend the path list explicitly if
  you need broader coverage.

---

## Source anchors

See [`CANONS.md`](./CANONS.md) §5 for the canonical citation list.
Foundational anchors only: Landauer 1961 (*IBM J. Res. Dev.* 5, 183),
Bennett 1973 (*IBM J. Res. Dev.* 17, 525) on reversible computing,
Friston 2010 (*Nat. Rev. Neurosci.* 11, 127) on the free energy
principle, plus the pre-registration / effect-size / CI methodology
references (COS, Cohen 1988, Lakens 2013, APA 7 §3.7). A 2026-04-25
audit struck five unverified 2025/2026 anchors; see CANONS.md §5 for
the audit note.
