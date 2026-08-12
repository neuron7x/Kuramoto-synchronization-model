# 11 — Distinguished Contribution Map

A single, defensible contribution stated at professorial altitude: not a result,
but a *method for governing whether a result is even permitted to exist*. The
body of work is the neuro/physics **operationalization ledger** + **law–mechanism
witness matrix** + **fail-closed claim-boundary gates**. Scope is admissibility,
not empirical truth (see `09` construct validity).

## D1 — The original method

A **machine-readable mechanism ledger** that binds, per mechanism, the full chain
formula → invariant (INV-*) → implementation symbol → witness test → falsifier →
artifact → limitation. Promotion to the OPERATIONAL tier is *refused* for any
mechanism that does not cite at least one `INV-*` contract from `CLAUDE.md`
together with an input contract, an output contract, a falsifier, and an existing
test path.

- Mechanism ledger: `.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml`
  (schema documented in its header; 32 entries).
- Derived, machine-readable matrix + traceability verdict:
  `artifacts/academy_fellow/law_mechanism_witness_matrix.json`,
  `artifacts/academy_fellow/traceability_report.json`
  (generator: `scripts/ci/gen_law_mechanism_witness_matrix.py`).
- Fail-closed runtime gate against biological-equivalence drift:
  `scripts/ci/check_neuro_claim_boundary.py`.
- Current distribution (matrix `summary`): **18 OPERATIONAL · 6 PARTIAL ·
  3 DECORATIVE · 2 OVERCLAIM · 2 LEGACY · 1 REJECTED**, with **0 open
  `missing_tests`** and `traceability_report.json` verdict **PASS**.

The discriminating design choice: `promotion_allowed` is a *function of binding*,
not of behaviour. A mechanism that runs correctly, has a witness test, and even
clears a null model is still held at PARTIAL if no `INV-*` contract names it. The
matrix records exactly this (`promotion_allowed: false` for every PARTIAL entry).

## D2 — Why it is nontrivial (the gate has teeth)

During the witness-hardening campaign (13 witness tests landed: 12 unit + 1
integration), four mechanisms were drafted for promotion PARTIAL → OPERATIONAL —
`dopamine-execution-adapter-tanh`, `neuro-optimizer-balance-metrics`,
`hebbian-plasticity-update`, `homeostatic-stabilizer`. Each had a new witness
test and an explicit non-claim, so the promotion *looked* earned.

The discipline reverted all four. They carry real behaviour and a passing witness,
but **no `INV-*` binding exists in `CLAUDE.md`**, so the binding rule forbids the
OPERATIONAL tier. The matrix preserves this verdict verbatim in each entry's
`witness_note`: *"Classification stays PARTIAL: no INV-* binding exists in
CLAUDE.md, so the repo neuro audit forbids OPERATIONAL promotion despite the added
witness — promotion is blocked on defining the invariant."* (`inv_refs: []`,
`promotion_allowed: false` for all four.)

This is the evidence that the method is not decorative: it caught and reversed an
over-promotion of its own author's work. A governance rule that has never blocked
the thing its author wanted is unfalsified governance.

## D3 — The gap it closes

**Admissibility is distinct from empirical truth.** A mechanism can be *witnessed*
(bounded output, deterministic replay, formula-derived tolerance, passing test)
without being *promoted* to a validated claim. Prior practice conflates the two:
a green test is read as license to assert the named scientific concept. This
ledger inserts a third state — witnessed-but-not-promoted — and makes it the
default. The closed gap is the silent slide from "the code does X and is tested"
to "X is a validated brain/physics model."

## D4 — Why generic CI / reproducibility tooling is insufficient

Standard CI, coverage gates, and reproducibility harnesses answer *"do the tests
pass?"* They cannot answer *"is this claim permitted to exist at this evidence
tier?"* — because that question depends on a binding from a prose invariant
contract to an implementation, not on test exit codes. Concretely:

- A passing witness test for the tanh dopamine adapter witnesses output ∈ [−1, 1].
  It does **not** authorise the word "dopamine" as a validated TD-error claim;
  only an `INV-*` binding would, and none exists — so CI-green coexists with
  PARTIAL.
- `check_neuro_claim_boundary.py` is orthogonal to coverage: it firewalls
  *biological-equivalence prose* in runtime source (a phrase like "basal ganglia
  simulation"), which no coverage tool inspects.
- The matrix `non_claims` block is enforced as structure, not asserted as text.

Generic tooling verifies execution; this method verifies *entitlement to claim*.

## D5 — Exact artifact per point

| Claim | Proving artifact (verified path) |
|---|---|
| Binding chain formula→INV→impl→witness→falsifier | `.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml` (entry schema in header) |
| Promotion = function of `INV-*` binding | `law_mechanism_witness_matrix.json` (`promotion_allowed` / `inv_refs` per entry) |
| Traceability verdict PASS, 0 open missing_tests | `artifacts/academy_fellow/traceability_report.json` |
| Reverted over-promotion (4 PARTIAL kept) | the four `witness_note` strings in the matrix + ledger entries |
| Distribution 18/6/3/2/2/1 | `law_mechanism_witness_matrix.json::summary.classification_distribution` |
| Biological-equivalence firewall (runtime) | `scripts/ci/check_neuro_claim_boundary.py` |
| Campaign narrative + honest findings | `artifacts/academy_fellow/ACADEMY_FELLOW_REPORT.md` |

> Note on the report: `ACADEMY_FELLOW_REPORT.md` narrates the *attempted* "4
> PARTIAL → OPERATIONAL" promotion. The authoritative end state is the
> ledger/matrix, where those four remain PARTIAL (`promotion_allowed: false`).
> The divergence is the audit trail of the revert in D2, not a contradiction to
> hide.

## Status discipline

This artifact is **not** a Distinguished-Professor-level result. It is an artifact
disciplined against Distinguished-Professor-style standards of originality,
evidence, reproducibility, and restraint.

**Binding non-claims (standing):**

- No biological equivalence — all neuro names are engineering analogs.
- No universal physics of markets; observers are not predictors.
- No alpha / profitability claim.
- No real L2 validation — synthetic-only witnesses; no recorded dataset/replay
  implied.
