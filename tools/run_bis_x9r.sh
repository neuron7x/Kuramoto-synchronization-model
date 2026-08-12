#!/bin/bash
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# End-to-end driver: BIS LBS bulk CSV → X-9R verdict on real data.
#
# Usage:
#   bash tools/run_bis_x9r.sh /path/to/WS_LBS_D_PUB_csv_flat.zip
#
# Produces:
#   /tmp/bis_real_data/dataset_dir/    (X-9R input)
#   /tmp/bis_real_data/empirical_falsification_capsule/  (X-9R output)

set -euo pipefail

BIS_ZIP="${1:-/tmp/bis_real_data/WS_LBS_D_PUB_csv_flat.zip}"
DATASET_DIR="${2:-/tmp/bis_real_data/dataset_dir}"
CAPSULE="${3:-/tmp/bis_real_data/empirical_falsification_capsule}"

if [ ! -f "$BIS_ZIP" ]; then
    echo "ERROR: BIS bulk zip not found at $BIS_ZIP" >&2
    echo "Download from: https://data.bis.org/static/bulk/WS_LBS_D_PUB_csv_flat.zip" >&2
    exit 1
fi

echo "[1/2] Building dataset_dir from BIS LBS bulk CSV ..."
python tools/build_bis_lbs_dataset.py \
    --bis-zip "$BIS_ZIP" \
    --output "$DATASET_DIR"

echo "[2/2] Running Protocol X-9R on real BIS data ..."
python -m research.systemic_risk.protocol_x9r run \
    --dataset-dir "$DATASET_DIR" \
    --output "$CAPSULE"
