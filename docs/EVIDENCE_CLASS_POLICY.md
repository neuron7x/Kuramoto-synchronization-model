<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Evidence-Class Contamination Policy (DAT-009)

**Rule in one line:** synthetic evidence can never populate an empirical claim
or a real-data manifest. Absence of a label is *not* empirical clearance.

## Canonical vocabulary (SSOT)

The closed set of evidence classes is defined once, in
[`governance/project_state.yaml`](../governance/project_state.yaml) (GOV-005).
Ordered by strength (strongest first):

| Class        | Strength | Meaning                                                                 |
|--------------|----------|-------------------------------------------------------------------------|
| `FACT`       | 4        | Externally verifiable, deterministic, enforced by an executable gate.   |
| `MEASURED`   | 3        | Real-data measurement with full provenance (dataset/config SHA, seed, null baseline). |
| `SIMULATION` | 2        | **Synthetic / seeded.** Instrumentation boundary only.                  |
| `HYPOTHESIS` | 1        | Proposed statement with a named falsifier, no executed measurement.     |
| `RETIRED`    | 0        | Falsified / withdrawn; a negative-evidence tombstone.                   |

`FACT` and `MEASURED` are **empirical**. `SIMULATION` is **synthetic**. This gate
reads the classes and strengths directly from the SSOT — it never hard-codes a
second copy — so the vocabulary can only change in one place.

## What the gate enforces

`scripts/ci/check_evidence_class.py` reads a manifest (or a directory of
manifests) of artifact records shaped `{id, evidence_class, backs_claim_class?}`
and **fails closed** on:

1. **`CROSS_CLASS_CONTAMINATION`** — an artifact backing a claim *stronger* than
   its own class. Strength monotonicity: an artifact of strength `s` may only
   back a claim of strength `<= s`. The canonical banned case is a `SIMULATION`
   artifact backing a `MEASURED` or `FACT` claim — "validated on synthetic data"
   is a contradiction.
2. **`MISSING_CLASS`** — a record with no `evidence_class`. An unlabeled artifact
   fails closed; absence is never empirical clearance.
3. **`UNKNOWN_CLASS`** — an `evidence_class` (or `backs_claim_class`) outside the
   ontology vocabulary. An unrecognised label cannot clear anything.
4. **`SYNTHETIC_IN_REAL_DATA_MANIFEST`** — a `SIMULATION` artifact listed in a
   manifest declared as real-data.

Every artifact is echoed in the JSON report with its class, so nothing passes
unseen or unlabeled.

## Manifest shapes

- A JSON list of records, or
- a JSON object with a `records` (or `artifacts`) list, optionally carrying
  `real_data: true` or `manifest_kind` in `{real_data, empirical, measured}`.
- A directory argument expands to every `*.json` file within.

A manifest is treated as **real-data** when the `--real-data` flag is passed, or
the manifest object declares it as above.

## Exit codes (fail-closed)

| Exit | Meaning                                                            |
|------|-------------------------------------------------------------------|
| `0`  | Clean — no contamination.                                          |
| `1`  | Flagged — contamination, missing, or unknown class found.         |
| `2`  | Error — unparseable SSOT/manifest, or a record with no `id`.      |

## Usage

```bash
# A real-data manifest may contain no SIMULATION artifact.
python scripts/ci/check_evidence_class.py --manifest datasets/real_data.json --real-data

# Scan every manifest in a results directory.
python scripts/ci/check_evidence_class.py --manifest results/
```

## Evidence

- Gate: `scripts/ci/check_evidence_class.py`
- Closure tests (negative + positive controls): `tests/ci/test_evidence_class.py`
- Worked audit showing the contamination case caught:
  [`artifacts/governance/evidence_class_audit.json`](../artifacts/governance/evidence_class_audit.json)

## Relationship to the claim-word firewall

This gate is the **data-side** complement to `scripts/ci/check_state_ontology.py`
(the claim-word firewall, which bans forbidden *marketing words* without a
backing class). GOV-005 forbids `SIMULATION`/`HYPOTHESIS`/`RETIRED` from backing
words like "validated"; DAT-009 forbids synthetic *artifacts* from backing
empirical *claims and manifests*. Same principle, two surfaces.
