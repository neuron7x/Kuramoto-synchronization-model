# Inference Transformer Implementation Plan

Read:

```text
AGENTS.md
README.md
PRODUCT_CATEGORY.md
CLAIMS.md
FORBIDDEN_CLAIMS.md
docs/REPOSITORY_SYSTEM.md
research_lines/ricci_microstructure_v1/contract.yaml
schemas/research/research_inference_artifact.schema.json
schemas/research/inference_transformer_contract.schema.json
configs/research/geosync_inference_transformer.v1.yaml
data/research/inference_transformer_blocks.v1.json
```

Add in the next code PR:

```text
scripts/ci/check_inference_transformer_contract.py
tests/ci/test_inference_transformer_contract.py
src/geosync/research/transformer/contracts.py
tests/research/transformer/test_contracts.py
```

Acceptance:

```text
YAML loads.
JSON loads.
Required keys are checked.
Certificate objects serialize to JSON.
Current research line stays HYPOTHESIS.
Placeholder examples stay non-evidence-bearing.
```

Verification target:

```bash
python -m json.tool schemas/research/inference_transformer_contract.schema.json >/dev/null
pytest -q tests/ci/test_inference_transformer_contract.py tests/research/transformer/test_contracts.py
```
