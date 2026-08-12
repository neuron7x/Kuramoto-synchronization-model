# Physics-2026 translation matrix

Source-of-truth: [`PHYSICS_2026_TRANSLATION.yaml`](../../../.claude/research/PHYSICS_2026_TRANSLATION.yaml)
Validator: [`tools/research/validate_physics_2026_translation.py`](../../../tools/research/validate_physics_2026_translation.py)
Tests: [`tests/research/test_validate_physics_2026_translation.py`](../../../tests/research/test_validate_physics_2026_translation.py)

Companion: [`source_validation.md`](source_validation.md)

## Why this exists

The translation matrix is the **methodological pattern → engineering
analog** mapping. It is NOT a metaphor table. Every entry is gated by
mechanical contracts that the validator enforces.

Each pattern names:

- the source(s) it borrows from
- the abstract methodological move it imports
- the GeoSync operational analog that re-uses that move
- a `proposed_module` path
- a `claim_tier` (FACT / ENGINEERING_ANALOG / HYPOTHESIS / REJECTED)
- an `implementation_status` (PROPOSED / IMPLEMENTED / REJECTED)
- the `measurable_inputs` runtime can produce
- the `output_witness` shape
- a `null_model` baseline behaviour
- a `falsifier` — the concrete observation that would unmake the claim
- the `deterministic_tests` required at module-implementation time
- a `mutation_candidate` — what the mutation harness would patch

## Six initial patterns (PR-1)

| Pattern | Sources | Tier | Status |
|---|---|---|---|
| `P1_POPULATION_EVENT_CATALOG` | S1 (GWTC-4) | ENGINEERING_ANALOG | PROPOSED |
| `P2_STRUCTURED_ABSENCE_INFERENCE` | S2 (pair-instability gap) | ENGINEERING_ANALOG | PROPOSED |
| `P3_DYNAMIC_NULL_MODEL` | S3 (DESI 2026) | ENGINEERING_ANALOG | PROPOSED |
| `P4_GLOBAL_PARITY_WITNESS` | S4 (Kitaev parity readout) | ENGINEERING_ANALOG | PROPOSED |
| `P5_MOTIONAL_CORRELATION_WITNESS` | S5 (helium motional Bell) | ENGINEERING_ANALOG | PROPOSED |
| `P6_COMPOSITE_BINDING_STRUCTURE` | S6 (doubly-charmed baryon) | ENGINEERING_ANALOG | PROPOSED |

All six are at `claim_tier: ENGINEERING_ANALOG` and
`implementation_status: PROPOSED`. PR-1 ships only the rail; the runtime
modules are deferred to PRs 2–7 (one module per PR).

## Validation contracts

The validator refuses any translation matrix that violates any of:

1. **Schema parse**: file must parse as YAML and declare `schema_version: 1`.

2. **Required keys per pattern**: `pattern_id`, `source_ids`,
   `source_fact_summary`, `methodological_pattern`,
   `geosync_operational_analog`, `proposed_module`, `claim_tier`,
   `implementation_status`, `measurable_inputs`, `output_witness`,
   `null_model`, `falsifier`, `deterministic_tests`,
   `mutation_candidate`, `ledger_entry_required`.

3. **Source references resolve**: every `source_ids` entry must exist
   in `docs/research/physics_2026/source_pack.yaml`.

4. **Non-REJECTED patterns must carry evidence**: at least one
   `measurable_input`, one `output_witness`, a non-empty `null_model`,
   a non-empty `falsifier`, and at least one `deterministic_test`.

5. **ENGINEERING_ANALOG bodies refuse forbidden phrasings**:
   ```
   "physical equivalence"
   "quantum market"
   "universal"
   "predicts returns"
   ```
   The scan covers `geosync_operational_analog`,
   `methodological_pattern`, `null_model`, `falsifier`. It deliberately
   does NOT cover `source_fact_summary` — that field may quote source
   phrasings (e.g. a paper title with the word "universal").

6. **HYPOTHESIS cannot be marked FACT** (cross-check via legacy fields).

7. **REJECTED patterns must include `rejection_reason`**.

8. **`proposed_module` paths are unique** across all patterns.

9. **`claim_tier` ∈ {FACT, ENGINEERING_ANALOG, HYPOTHESIS, REJECTED}**.

10. **`implementation_status` ∈ {PROPOSED, IMPLEMENTED, REJECTED}**.

## Tier semantics

| Tier | Means | Allowed status |
|---|---|---|
| `FACT` | The pattern is a verified physical fact about GeoSync's runtime. Reserved for entries with mutation-killed tests + integration evidence. | IMPLEMENTED only |
| `ENGINEERING_ANALOG` | We borrow the discipline of the source pattern. Engineering claim, not physical. The default tier for everything in PR-1. | PROPOSED / IMPLEMENTED |
| `HYPOTHESIS` | Possible but not yet engineered. Needs at least a measurable_input and a falsifier before it can be promoted. | PROPOSED |
| `REJECTED` | Pattern fails one of the gating conditions. Kept as a negative reference. | REJECTED |

The validator refuses `FACT` claim_tier in PR-1 entirely, by virtue of
the requirement that an IMPLEMENTED status accompany it. Module PRs
will introduce IMPLEMENTED status one pattern at a time.

## Running

```bash
# Validate the shipping translation matrix against the shipping source pack:
python tools/research/validate_physics_2026_translation.py

# Custom paths:
python tools/research/validate_physics_2026_translation.py \
    --translation .claude/research/PHYSICS_2026_TRANSLATION.yaml \
    --source-pack docs/research/physics_2026/source_pack.yaml \
    --output /tmp/geosync_physics2026_translation_validation.json

# Tests:
python -m pytest tests/research/test_validate_physics_2026_translation.py -q
```

Exit code is `0` on a clean translation, non-zero otherwise. The JSON
report is written even on failure.

## Adding a pattern

1. Confirm at least one source in the source pack supports the pattern.
2. Add a new `pattern_id` (shape: `P<digit>_<UPPER_TOKEN>`).
3. Provide every required key. Keep `claim_tier` at
   `ENGINEERING_ANALOG` until module + tests + mutation kill exist.
4. Run the validator.
5. Open the implementation PR (per the PR-2..PR-7 sequence).

## Promoting a pattern to IMPLEMENTED

When the runtime module ships:

1. Implement the module per the [module template](#module-template-recap)
   (input dataclass, witness dataclass, pure assess function, six tests).
2. Set `implementation_status: IMPLEMENTED`.
3. Add a corresponding entry to the claim ledger
   (`.claude/claims/CLAIMS.yaml`) with the pattern_id as `claim_id`
   prefix.
4. Add a mutation candidate to
   `.claude/mutation/MUTATION_LEDGER.yaml` and confirm it is killed.

## Rejecting a pattern

If a pattern fails one of the gating conditions during module work:

1. Set `claim_tier: REJECTED` AND `implementation_status: REJECTED`.
2. Set `rejection_reason` describing the evidence gap.
3. Do NOT delete the entry. Negative references prevent the same
   failed pattern from re-emerging under a different name.

## Module template (recap)

Every module that follows from this matrix MUST have:

- module docstring naming `pattern_id`, `engineering analog`, and an
  explicit non-claim section ("does NOT claim physical equivalence")
- input dataclass with units, finite validation, no hidden mutable
  defaults
- witness dataclass with status / tier / reason / falsifier /
  evidence_fields / uncertainty
- assess function: deterministic, pure, no network, no clock, no
  random, no file mutation
- tests: positive, negative, boundary, invalid input, falsifier,
  no-overclaim

## What the matrix explicitly does NOT do

- It does NOT translate physics into product features. The downstream
  modules are engineering analogs of methodological discipline, not
  ports of physical phenomena. We borrow the discipline of pair-
  instability inference, not the gap itself.
- It does NOT use the word "quantum" in any runtime module name. The
  validator enforces that against ENGINEERING_ANALOG bodies.
- It does NOT promote any pattern beyond ENGINEERING_ANALOG. Promotion
  to FACT requires mutation-killed tests + integration evidence
  (per the calibration layer's claim ledger rules); that comes later.

## Origin

Physics-2026 integration was authorised after the 2026-04-26 audit
codified the calibration layer (claim ledger, evidence matrix,
dependency truth, false-confidence detector, security reachability,
mutation kill ledger, architecture boundaries, system truth report).
The translation matrix is the next layer up: how the system imports
*external* methodological discipline as an independent witness of its
own engineering blind spots.

The validator is the mechanical guarantee that this discipline is not
ornamental. Every pattern must pay its falsifier and its test before it
gets a runtime line.
