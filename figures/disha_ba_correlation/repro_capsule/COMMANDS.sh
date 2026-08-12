#!/bin/bash
set -euo pipefail
python tools/build_disha_ba_correlation_figures.py \
  --dataset-dir /tmp/bis_real_data/dataset_dir_v2 \
  --output-dir figures/disha_ba_correlation \
  --normal-start 2006Q1 \
  --normal-end 2007Q4 \
  --lehman-start 2008Q3 \
  --lehman-end 2009Q2 \
  --sensitivity-start 2007Q1 \
  --sensitivity-end 2009Q4 \
  --edge-quantile 0.85 \
  --top-n-labels 12 \
  --ba-simulations 200 \
  --min-risk-total-strength 100000.0 \
  --min-effective-change-observations 8 \
  --seed 42
