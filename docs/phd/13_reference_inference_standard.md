# 13 — Reference Standard for Verified-Inference Discipline

This chapter is the **canonical reference standard** (the *еталон*) for how a
mechanism becomes an admissible claim in this repository. It is deliberately a
standard of **evidence discipline, reproducibility, and restraint** — the
highest tier this artifact can honestly occupy — and **not** a standard of
empirical or market truth.

It does not introduce new science, a new solver, or a new runtime subsystem. It
*names* and *unifies* the gates that already exist (see chapters `02`, `03`,
`04`, `10`, `12`) into one auditable contract, and binds that contract to a
machine-generated conformance certificate so the standard is enforced rather
than aspirational.

## Scope and limits (read first)

- **Tier:** admissibility / evidence discipline. A mechanism that passes this
  standard is *permitted to exist as a claim at its declared tier* — it is not
  thereby true, nor a market or biological fact.
- **Data:** synthetic-only. No real L2 dataset or replay is implied.
- **Bound:** the standard governs *claims about the repository's own
  mechanisms*; it makes no statement about markets or biology.

## The claim-tier ladder

| Tier | Ledger class | Meaning | Gate |
|------|--------------|---------|------|
| Promoted claim | `OPERATIONAL` | invariant-bound, contract + falsifier + witness test present | `neuro_symbolic_audit.py` |
| Admissible, not promoted | `PARTIAL` | witnessed, but an open remediation blocks promotion | `neuro_symbolic_audit.py` |
| Quarantined | `DECORATIVE` / `OVERCLAIM` / `LEGACY` | naming/record only; explicit non-claim | claim-boundary walls |
| Negative result | `REJECTED` | retained as scientific value (chapter `12`) | falsifier ledger |

Physics inference readiness has its own honest verdict ladder
(`READY_SYNTHETIC_ONLY` …) emitted by `scripts/ci/check_physics_inference_readiness.py`;
claim maturity rungs (`MEASURED_SYNTHETIC` …) by `scripts/ci/check_claim_maturity.py`.

## The per-claim eight-layer contract

Every promoted mechanism must carry, end to end:

1. **Law / mechanism** — the named principle.
2. **Formula** — the closed form.
3. **Validity domain** — where it holds; out-of-domain input is refused, not coerced.
4. **Input contract** · 5. **Output contract** — bounds asserted, not assumed.
6. **Falsifier** — an executable refutation; a tolerance is formula-derived, never magic.
7. **Witness test** — a passing test that exercises the falsifier.
8. **Artifact + replay** — a committed receipt and a one-line replay command.

This is the same chain the witness matrix
(`artifacts/academy_fellow/law_mechanism_witness_matrix.json`) and the
international-standard evidence table
(`artifacts/academy_fellow/distinguished_evidence_table.json`) record per
mechanism, anchored to Popper (falsifiability), ACM Artifact Badging
(Functional / Results-Reproduced), and FAIR.

## The seven invariant laws (machine-enforced)

| Law | Statement | Enforcing gate |
|-----|-----------|----------------|
| **L1** Admissibility ≠ promotion | a witnessed mechanism is admissible, not promoted, until fully bound | `neuro_symbolic_audit.py` (0 open `missing_tests`) |
| **L2** No promotion without invariant | no `OPERATIONAL` claim without ≥1 `INV-*` binding | `neuro_symbolic_audit.py` |
| **L3** Falsification-first | every promoted/partial claim declares an executable falsifier | `check_falsifier_ledger.py` |
| **L4** No-overclaim wall | biological-equivalence and product-category overclaims are firewalled | `check_neuro_claim_boundary.py` + `check_claim_boundary.py` |
| **L5** One-command reproducibility | the full battery runs from `make phd-evidence` | `scripts/ci/phd_evidence.sh` |
| **L6** Witness completeness | every `OPERATIONAL` claim has ≥1 witness test and a non-empty falsifier; no claim rests on exit codes | `check_invariant_source_binding.py` |
| **L7** Partial has remediation | every `PARTIAL` declares an active (non-`KEEP`) remediation | `neuro_symbolic_audit.py` |

Each law is checked against repository facts — not asserted — by
`scripts/ci/gen_reference_conformance.py`, which emits
`artifacts/academy_fellow/reference_conformance_certificate.json` with a
per-law verdict and an overall `CONFORMANT` / `NON_CONFORMANT` result.

## How the standard caught itself (worked exemplar)

The standard is credible because it has refused real work, including the
author's own. During the witness campaign (PR #1308) four mechanisms were
prematurely promoted `PARTIAL → OPERATIONAL` with empty `inv_refs`; the L2 gate
rejected the build and the promotions were reverted to `PARTIAL` (chapter `12`).
Admissibility did not become a claim. That episode — not a green badge — is the
evidence that the gate has teeth.

## Conformance procedure

```bash
make phd-evidence            # runs the full fail-closed battery + regenerates artifacts
python scripts/ci/gen_reference_conformance.py   # emits the conformance certificate
```

A change conforms to this standard iff `make phd-evidence` is green **and** the
certificate verdict is `CONFORMANT`. Either failing blocks the claim, not just
the merge.

## Status discipline

This standard, and any artifact certified against it, is **disciplined against
Distinguished-Professor-style standards of originality, evidence,
reproducibility, and restraint** — it is **not** a claim of a
Distinguished-Professor-level result, and not a claim of empirical truth.

**Binding non-claims:** no biological equivalence; no universal physics of
markets; no alpha/profitability/edge; no `B.wheel=0`; synthetic-only witnesses.
