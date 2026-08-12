# Physics-2026 source-validation protocol

Source-of-truth: [`source_pack.yaml`](source_pack.yaml)
Validator: [`tools/research/validate_physics_2026_sources.py`](../../../tools/research/validate_physics_2026_sources.py)
Tests: [`tests/research/test_validate_physics_2026_sources.py`](../../../tests/research/test_validate_physics_2026_sources.py)

## Why this exists

The Physics-2026 integration is gated by an **evidence rail**, not by
metaphor. Before any GeoSync runtime module borrows a methodological
pattern from a 2026 physics result, the pattern's source must be
recorded here with three explicit components:

- **`verified_fact`** — what the source text actually establishes
- **`allowed_translation`** — the methodological pattern that may be
  re-used in engineering
- **`forbidden_overclaim`** — the exact phrasings that this entry must
  NOT be used to support

The validator enforces those components mechanically. A new source
cannot enter the rail without all three.

## Six initial sources

| ID | Title | Provenance |
|---|---|---|
| `S1_GWTC4` | GWTC-4.0: Updating the Gravitational-Wave Transient Catalog | LIGO Scientific Collaboration / Virgo / KAGRA |
| `S2_PAIR_INSTABILITY_GAP` | Evidence of the pair-instability gap from black-hole masses | Nature, 2026 |
| `S3_DESI_2026` | DESI reaches mapping milestone | DESI / LBNL |
| `S4_KITAEV_PARITY_READOUT` | Single-shot parity readout of a minimal Kitaev chain | Nature, 2025 |
| `S5_HELIUM_MOTIONAL_BELL` | Bell correlations in momentum-entangled massive helium atoms | Nature Communications, 2026 |
| `S6_LHCB_DOUBLY_CHARMED_BARYON` | LHCb Collaboration discovers new proton-like particle | CERN / LHCb |

Each entry's `verified_fact` lists are derived directly from the cited
source. They are NOT paraphrases of secondary commentary.

## Validation contracts (six)

The validator refuses any source pack that violates any of:

1. **Schema parse**: file must parse as YAML and declare `schema_version: 1`.
2. **Required keys per source**: `source_id`, `title`, `url`,
   `verified_fact`, `allowed_translation`, `forbidden_overclaim`.
3. **Non-empty evidence lists**: each of the three evidence lists
   (`verified_fact`, `allowed_translation`, `forbidden_overclaim`)
   must contain at least one entry.
4. **No forbidden phrasings** in `title` / `verified_fact` /
   `allowed_translation`. The five forbidden phrasings are:
   ```
   "proves market"
   "quantum market"
   "predicts returns"
   "universal law"
   "physical equivalence"
   ```
   These are NOT scanned inside `forbidden_overclaim` — that field
   exists precisely to forbid them by quoting them.
5. **Stable, unique `source_id`**: matches `S<digits>_<UPPER_TOKEN>`.
   Duplicates are rejected.
6. **Deterministic JSON output** to
   `/tmp/geosync_physics2026_source_validation.json`. Same inputs →
   byte-identical bytes, sorted keys, sorted source_ids.

## Running

```bash
# Validate the shipping source pack:
python tools/research/validate_physics_2026_sources.py

# Custom paths:
python tools/research/validate_physics_2026_sources.py \
    --pack docs/research/physics_2026/source_pack.yaml \
    --output /tmp/geosync_physics2026_source_validation.json

# Tests for the validator:
python -m pytest tests/research/test_validate_physics_2026_sources.py -q
```

Exit code is `0` on a clean pack, non-zero on any violation. The JSON
report is written even on failure so CI can persist evidence.

## Adding a source

1. Cite a primary peer-reviewed or institutional URL.
2. State at least one `verified_fact`, one `allowed_translation`, and
   one `forbidden_overclaim`. Phrase verified facts conservatively;
   prefer source quotation over paraphrase.
3. Run `python tools/research/validate_physics_2026_sources.py`.
4. The new source becomes referenceable in the translation matrix
   (`.claude/research/PHYSICS_2026_TRANSLATION.yaml`).

## Retiring a source

Add `retired: true` to the source entry rather than deleting it. The
validator currently treats retired sources identically to active ones,
but downstream tools (translation validator, future ledger entries)
may distinguish them. Removing a source breaks the audit trail and is
not allowed.

## What the rail explicitly does NOT do

- It does NOT vet the physics. The validator only checks that the
  declarations exist and do not overclaim. The PHYSICS is upstream and
  is the responsibility of the cited source's authors and reviewers.
- It does NOT score sources. The rail is ordinal: a source is either
  in or out. Within the rail, all sources have the same epistemic
  weight by default; per-pattern weight comes from the translation
  matrix.
- It does NOT translate sources into runtime modules. That is the
  translation matrix's job. Sources record *what is true upstream*;
  translations record *what we propose to engineer downstream*.
- It does NOT permit verbal correspondence (e.g. "asset cluster" =
  "doubly-charmed baryon"). Translation is methodological pattern
  re-use, not entity mapping. The forbidden-overclaim entries enforce
  this at the per-source level.

## Origin

The 2026-04-26 audit established that GeoSync's strongest historical
failure mode was **claim inflation through metaphor** — borrowing a
physics word to describe an engineering behaviour without paying the
falsifier and the test. The Physics-2026 integration explicitly refuses
that path: every translation is gated by a verified source, and every
runtime module that follows will be gated by the translation matrix.

This is the discipline-import side of the work. The companion document
[`translation_matrix.md`](translation_matrix.md) covers the
analog-export side.
