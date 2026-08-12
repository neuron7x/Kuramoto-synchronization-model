# GeoSync Inference Transformer Control Plane

Status: RESEARCH-ONLY / CONFIGURATION-FIRST / IMPLEMENTATION-AGENT READY.

This file is the human-readable index for the v1 control-plane seed.

Canonical machine surfaces:

```text
schemas/research/inference_transformer_contract.schema.json
configs/research/geosync_inference_transformer.v1.yaml
data/research/inference_transformer_blocks.v1.json
.claude/handoffs/inference-transformer-control-plane.md
.claude/commit_acceptors/inference-transformer-control-plane.yaml
```

Core flow:

```text
observation -> graph_snapshot -> geometry_state -> regime_certificate -> research_artifact
```

Implementation order:

```text
1. Validate the schema, YAML config, and JSON block map.
2. Add typed certificate objects.
3. Add a deterministic placeholder pipeline.
4. Add tests for valid and invalid contracts.
5. Wire a CI guard after local validation passes.
```

Non-goals:

```text
- no claim-tier upgrade
- no real-data evidence claim
- no dependency-heavy transformer library
- no weakening of existing claim-boundary gates
```

The next implementation agent should treat the YAML and JSON files as the source of operational truth for the first code PR.
