# Ricci Microstructure v1

`ricci_microstructure_v1` tests whether Ollivier-Ricci curvature on real L2 order-book graphs carries signal beyond null baselines.

Claim tier: **T3 / NOVEL / EXPLORATORY / FALSIFIABLE**.

This is not validated alpha, not a production trading signal, and not confirmed market physics.

## Commands

```bash
geosync-research ingest --data data/l2_manifest.json
geosync-research run --line ricci_microstructure_v1 \
  --config configs/research/ricci_microstructure_v1.json \
  --data data/validated_l2_frame.parquet \
  --out artifacts/runs \
  --seed 1337
geosync-research verify RUN_ID
```

## Graph contract

- NetworkX `DiGraph`
- nodes: bid and ask price levels
- edges: same-side depth links and bid/ask cross-level links
- default edge signal: NOBI

```text
NOBI = (Depth_bid - Depth_ask) / (Depth_bid + Depth_ask)
```

Each edge must contain `ricciCurvature` after inference.

## Statistical gate

A result is `SUPPORTED` only when:

```text
p_value < 0.01 AND abs(cliffs_delta) >= 0.147
```

Otherwise the valid falsification result is `HYPOTHESIS_NOT_SUPPORTED`.
