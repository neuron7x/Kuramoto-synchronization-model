# GeoSync Research Standard Review Packet

## Status

`DRAFT`.

## Review target

Evaluate whether the research-standard layer is ready to govern a future public standard release.

## Required artifacts

```text
configs/research/geosync_research_standard.v1.yaml
schemas/research/research_standard_contract.schema.json
data/research/research_standard_layers.v1.json
manifests/research/dynamic_universe.v1.json
manifests/research/reproduction_badge.v1.json
manifests/research/release_provenance.v1.json
manifests/research/cost_latency_assumptions.v1.json
```

## Reviewer questions

1. Are data-lineage assumptions explicit enough to avoid survivor-only interpretation?
2. Are reproduction states separated from mere artifact availability?
3. Are cost and latency assumptions explicit before any utility-oriented interpretation?
4. Are provenance fields sufficient for a citable release candidate?
5. Does the layer preserve `HYPOTHESIS` status for `ricci_microstructure_v1`?

## Verification

```bash
python scripts/ci/check_research_standard_contract.py
pytest -q tests/ci/test_research_standard_contract.py
```

⊛
