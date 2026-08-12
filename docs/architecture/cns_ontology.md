# CNS Control Ontology

GeoSync defines a canonical witness-first control ontology in:

- Schema: `schemas/cns/control_ontology.schema.json`
- Payload: `configs/cns/control_ontology.v1.json`
- Stream registry: `configs/cns/stream_registry.v1.json`
- Guard: `scripts/check_cns_ontology_usage.py`

## Contract

Every control variable MUST define:

- `name`
- `role` (`witness_state`, `actor_state`, `coherence_state`, `risk_state`)
- `axis` (`Intent`, `Time`, `Energy`, `Error`, `Control`)
- `source`
- `units`
- `owner_module`
- `contradiction_event`
- `flow` (`mode=stream`, `source_stream`, `cadence_ms`, `max_staleness_ms`, `lag_tolerance_ms`)

## Invariants

1. The ontology MUST contain all five coherence axes.
2. Variable names MUST be unique.
3. All four control roles (`witness_state`, `actor_state`, `coherence_state`, `risk_state`) MUST be represented.
4. Every variable MUST map to one coherence axis.
5. Every variable MUST define a canonical contradiction event (`HiddenContradiction.*`) for observability.
6. Every `owner_module` MUST resolve to an existing repository module path.
7. Every variable MUST be represented as a dynamic stream contract; static constants are not valid ontology entries.
8. Every `flow.source_stream` MUST be declared in the stream registry, and ontology cadence/staleness cannot violate stream SLA bounds.

## Usage

Run the guard locally:

```bash
python scripts/check_cns_ontology_usage.py
```

The guard is intentionally self-contained (Python stdlib only) so validation does not depend on external lint-time libraries.

Run tests for the guard:

```bash
pytest tests/test_cns_ontology_guard.py -q
```
