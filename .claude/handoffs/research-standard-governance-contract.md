# Research Standard Contract Handoff

## Scope

This stacked PR adds a public-research-standard governance layer on top of PR #1204.

Keep `ricci_microstructure_v1` at `HYPOTHESIS`.

## First read order

1. `configs/research/geosync_research_standard.v1.yaml`
2. `schemas/research/research_standard_contract.schema.json`
3. `data/research/research_standard_layers.v1.json`
4. `manifests/research/dynamic_universe.v1.json`
5. `manifests/research/reproduction_badge.v1.json`
6. `manifests/research/release_provenance.v1.json`
7. `manifests/research/cost_latency_assumptions.v1.json`
8. `scripts/ci/check_research_standard_contract.py`
9. `tests/ci/test_research_standard_contract.py`

## Verification

```bash
python -m json.tool schemas/research/research_standard_contract.schema.json >/dev/null
python scripts/ci/check_research_standard_contract.py
pytest -q tests/ci/test_research_standard_contract.py
```

## Next seam

Generate `review/research_standard_review_packet.md` from the manifests after the focused workflow is green.

⊛
