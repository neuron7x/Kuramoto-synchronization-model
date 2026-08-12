#!/bin/bash
set -euo pipefail

PYTHONPATH=. python research/askar/sentiment_node_ricci_graph.py \
  --panel data/askar_full/panel_hourly_extended.parquet \
  --output results/sentiment_node_verdict.json \
  --source vix

echo "Verdict:"
cat results/sentiment_node_verdict.json | python -m json.tool
