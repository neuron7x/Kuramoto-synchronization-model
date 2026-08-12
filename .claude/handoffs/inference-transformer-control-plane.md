# Inference Transformer Control Plane Handoff

## Scope

Continue PR #1204 as a research-only control-plane implementation.

`ricci_microstructure_v1` remains `HYPOTHESIS`.

## First read order

1. `.claude/value_functions/n7x_value_functions.v1.yaml`
2. `configs/research/geosync_inference_transformer.v1.yaml`
3. `schemas/research/inference_transformer_contract.schema.json`
4. `data/research/inference_transformer_blocks.v1.json`
5. `scripts/ci/check_inference_transformer_contract.py`
6. `tests/ci/test_inference_transformer_contract.py`
7. `src/geosync/research/transformer/contracts.py`
8. `src/geosync/research/transformer/pipeline.py`
9. `tools/research/run_inference_transformer_demo.py`
10. `artifacts/runs/ricci_microstructure_v1/inference_transformer_placeholder.json`
11. `.github/workflows/inference-transformer-contract.yml`

## Required verification

```bash
python -m json.tool schemas/research/inference_transformer_contract.schema.json >/dev/null
python scripts/ci/check_inference_transformer_contract.py
python tools/research/run_inference_transformer_demo.py
pytest -q tests/ci/test_inference_transformer_contract.py
```

## Acceptance

- Contract validator exits zero on committed seed files.
- Typed certificate objects preserve boundary semantics.
- Demo emits a placeholder artifact only.
- Focused CI workflow runs without network services.
- Value functions guide decisions; tests remain the acceptance authority.

## Next implementation seam

After focused CI is green, either wire semantic artifact validation into the focused workflow or add the first deterministic graph-snapshot adapter with null inputs.

⊛
