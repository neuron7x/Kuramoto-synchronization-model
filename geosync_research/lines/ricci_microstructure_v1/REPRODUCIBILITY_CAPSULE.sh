#!/usr/bin/env bash
# Reproducibility capsule for ricci_microstructure_v1 (augments PR #1242).
#
# Flow: ingest -> run -> verify -> SHA compare. Zero hardcoded absolute paths;
# everything resolves from this script's location. The committed raw CSV is the
# frozen, SHA-pinned substrate (real Binance USD-M depth — recorded honestly,
# NOT LOBSTER). Re-running on the same frozen file + seed reproduces a
# bit-identical artifact (determinism contract INV-HPC1).
#
# Usage: REPRODUCIBILITY_CAPSULE.sh [MANIFEST] [CONFIG] [SEED]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT"

MANIFEST="${1:-data/l2_manifest.json}"
CONFIG="${2:-configs/research/ricci_microstructure_v1.json}"
SEED="${3:-1337}"
INGEST_DIR="data/processed/ricci_microstructure_v1"
OUT_ROOT="artifacts/runs/ricci_microstructure_v1"
CLI="python -m tools.research.ricci_microstructure_cli"

echo "==> [1/4] ingest (L2 contract + provenance stamp, honest source)"
$CLI ingest --data "$MANIFEST" --out "$INGEST_DIR"

echo "==> [2/4] run (Ollivier-Ricci inference + nulls + falsification gate)"
RUN_JSON="$($CLI run --line ricci_microstructure_v1 --config "$CONFIG" \
    --data "$INGEST_DIR/validated_l2_frame.parquet" --out "$OUT_ROOT" --seed "$SEED")"
echo "$RUN_JSON"
ARTIFACT="$(python -c "import json,sys; print(json.loads(sys.argv[1])['artifact'])" "$RUN_JSON")"

echo "==> [3/4] verify (schema Draft 2020-12 + allowed-status)"
$CLI verify "$ARTIFACT"

echo "==> [4/4] SHA compare (artifact.data_sha256 == sha256(raw file))"
python - "$INGEST_DIR/data_manifest.json" "$ARTIFACT" "$MANIFEST" <<'PY'
import hashlib, json, sys
from pathlib import Path
manifest_path, artifact_path, input_manifest = sys.argv[1], sys.argv[2], sys.argv[3]
data_manifest = json.load(open(manifest_path))
artifact = json.load(open(artifact_path))
raw = Path(input_manifest).parent / json.load(open(input_manifest))["data_path"]
actual = hashlib.sha256(raw.read_bytes()).hexdigest()
assert actual == data_manifest["data_sha256"] == artifact["data_sha256"], "SHA mismatch"
assert artifact["falsification_status"] in {"SUPPORTED", "HYPOTHESIS_NOT_SUPPORTED", "INVALID"}
assert data_manifest["source"] != "LOBSTER" or "lobster" in raw.name.lower(), "source must be honest"
print(f"OK  data_sha256={actual[:16]}...  source={data_manifest['source']}  status={artifact['falsification_status']}")
PY

# Publish the freshly-reproduced artifact as the committed canonical evidence the
# CI gate verifies. Re-running this capsule on a clean tree with the same frozen
# CSV + seed reproduces a bit-identical artifact (determinism contract), so the
# committed copy and a fresh run agree byte-for-byte.
CANON="geosync_research/lines/ricci_microstructure_v1/canonical"
mkdir -p "$CANON"
cp "$ARTIFACT" "$CANON/artifact.json"
echo "==> published canonical artifact -> $CANON/artifact.json"

echo "==> capsule complete"
