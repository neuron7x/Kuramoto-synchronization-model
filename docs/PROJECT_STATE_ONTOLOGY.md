---
doc_status:
  status: current
  authoritative_for:
    - project_maturity_state
    - claim_word_firewall
  valid_from: 2026-07-16
  # This is the doc that DEFINES the forbidden claim-word vocabulary, so it
  # names those words on purpose. It is recorded (not scanned) by the gate.
  defines_claim_vocabulary: true
  generated_by: null
---

# Project-State Ontology (GOV-005)

Formal, machine-readable ontology of GeoSync's project maturity and the claim
words the project is allowed to use. This closes remediation item **GOV-005**
("Визначити формальну онтологію станів проєкту та claims") and unblocks the
RES / DAT / DOC downstream items that depend on a single, checkable definition
of "what state are we in" and "which words are we allowed to say".

## Single source of truth

[`governance/project_state.yaml`](../governance/project_state.yaml) is the
**SSOT**. Nothing else declares the project's maturity state or the claim-word
firewall; every status surface is generated from it and every gate reads it.

| Concern | Where |
| --- | --- |
| Maturity ladder + current state | `governance/project_state.yaml` → `maturity_states`, `current_state` |
| Evidence-class vocabulary | `governance/project_state.yaml` → `evidence_classes` |
| Forbidden-claim → required-evidence map | `governance/project_state.yaml` → `forbidden_claims` |
| Status badge / markdown renderer | `scripts/ci/gen_status_surfaces.py` |
| Claim-boundary gate | `scripts/ci/check_state_ontology.py` |
| Closure tests | `tests/ci/test_state_ontology.py` |

## Maturity states

Ascending; no state may be skipped. `current_state` names the rung the project
as a whole honestly sits at. GeoSync's live claims are synthetic-/single-session
only (`PRODUCT_CATEGORY.md`, `NO_DEPLOY`), so the honest project rung is
`RESEARCH_ALPHA`.

| Rank | State | Meaning (short) |
| --- | --- | --- |
| 0 | `RESEARCH_ALPHA` | Instrumentation exists; evidence synthetic / single-session. Not deployable. |
| 1 | `REPEATABLE` | Same author + machine → bit-identical re-run (seed + replay digest). |
| 2 | `REPRODUCIBLE` | Independent operator reproduces from recorded provenance. |
| 3 | `REPLICATED` | Independent dataset/session/venue confirms vs null + simpler baseline. |
| 4 | `RELEASE_CANDIDATE` | All gates green, external replication, negatives preserved, cost model passed. |
| 5 | `PRODUCTION` | Deployed and operating on real data with live monitoring. |

## Evidence classes

Ordered by strength. A forbidden claim word is admissible only when the
surrounding claim declares one of the classes its firewall entry `requires`.

| Class | Backs a status word? | Meaning (short) |
| --- | --- | --- |
| `FACT` | yes (strongest) | Deterministic, gate-enforced repository state (counts, hashes, raised contracts). |
| `MEASURED` | yes | Real-data measurement with full provenance + null baseline. |
| `SIMULATION` | **no** | Synthetic / seeded measurement. Instrumentation boundary only. |
| `HYPOTHESIS` | **no** | Proposed statement with a falsifier but no executed measurement. |
| `RETIRED` | **no** | Falsified / withdrawn claim, kept as a negative-evidence tombstone. |

The central anti-pattern this catches: *"validated" (or "production-grade",
"proven", "deployable", …) asserted on `SIMULATION` / `HYPOTHESIS` / no
evidence at all.* Synthetic evidence never backs a status word.

## The claim-word firewall

Words are drawn from [`FORBIDDEN_CLAIMS.md`](../FORBIDDEN_CLAIMS.md) ("Banned
Status Language") and `scripts/ci/lint_forbidden_terms.py` (IERD trigger
terms). This ontology adds the machine-readable `claim → required-evidence`
binding those documents lacked.

`check_state_ontology.py` takes text plus a *declared* evidence class and flags
every forbidden word whose declared class is not among its `requires` set. A
forbidden word with **no** declared class is always a contradiction — a status
word with no backing evidence is exactly what the gate exists to catch. The
gate fails **closed**: a malformed SSOT or an out-of-vocabulary evidence class
exits with an error, never a silent pass.

## Usage

```bash
# Validate the SSOT is internally consistent.
python scripts/ci/check_state_ontology.py --validate

# Claim-boundary check: text + declared evidence class.
python scripts/ci/check_state_ontology.py \
    --check-text "the result is validated" --evidence-class MEASURED   # PASS
python scripts/ci/check_state_ontology.py \
    --check-text "the result is validated"                             # FLAGGED (no class)

# Scan a file under a declared class.
python scripts/ci/check_state_ontology.py --check-file README.md --evidence-class HYPOTHESIS

# Generate status surfaces FROM the SSOT.
python scripts/ci/gen_status_surfaces.py                 # markdown -> stdout
python scripts/ci/gen_status_surfaces.py --format badge  # badge line -> stdout
python scripts/ci/gen_status_surfaces.py --out generated/PROJECT_STATUS.md

# Closure tests.
python -m pytest tests/ci/test_state_ontology.py -q
```

## Scope and residuals

- **Not wired into README / CITATION.cff.** Generating those surfaces from the
  SSOT (and gating their claim words) is a downstream **DOC** task; this item
  delivers the SSOT, generator, gate, and closure tests only. The generator
  can already render a README status fragment (`--out`), but wiring it in is
  deliberately left to the DOC workstream to avoid central-file collisions.
- **Relationship to `analytics/signals/claim_maturity.py`.** That module is the
  per-descriptor 14-rung *evidence ladder* for individual research lines. This
  ontology is the coarser *project-level* maturity state plus the claim-word
  firewall — complementary, not a duplicate.
- The gate matches literal claim words; it does not do semantic paraphrase
  detection. Extending the pattern list is an additive edit to the SSOT.
