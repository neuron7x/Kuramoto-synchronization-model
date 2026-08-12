#!/bin/bash
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
#
# Fail-closed deterministic verification script for the GeoSync canonical-seven
# release candidate. From a clean clone, runs the same checks the
# author runs in verify mode and emits EXPECTED_OUTPUTS_actual.json for diff
# against EXPECTED_OUTPUTS.json.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# 1. Static analysis
python -m mypy --strict research/systemic_risk/ tools/ \
    > REPRODUCIBILITY_CAPSULE/MYPY_REPORT_actual.txt 2>&1
python -m ruff check research/systemic_risk/ tools/ tests/ \
    > REPRODUCIBILITY_CAPSULE/RUFF_REPORT_actual.txt 2>&1
python -m black --check research/systemic_risk/ tools/ tests/ \
    > REPRODUCIBILITY_CAPSULE/BLACK_REPORT_actual.txt 2>&1

# 2. Test suite — produce junit XML for stable diff
mkdir -p REPRODUCIBILITY_CAPSULE/test_artefacts
python -m pytest \
    tests/research/systemic_risk/ \
    tests/metamorphic/ \
    tests/negative_controls/ \
    -q \
    --junitxml=REPRODUCIBILITY_CAPSULE/test_artefacts/TEST_REPORT_actual.xml \
    > REPRODUCIBILITY_CAPSULE/test_artefacts/PYTEST_STDOUT_actual.txt 2>&1

# 3. Research-integrity gates
python tools/check_public_symbol_matrix.py \
    > REPRODUCIBILITY_CAPSULE/test_artefacts/SYMBOL_MATRIX_actual.txt 2>&1
python tools/compile_claims.py --fail-on-floating \
    > REPRODUCIBILITY_CAPSULE/test_artefacts/CLAIMS_COMPILE_actual.txt 2>&1

# 4. X-9R smoke run
python -c "
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location(
    'h', 'tests/research/systemic_risk/test_protocol_x9r.py'
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod._build_clean_dataset(Path('REPRODUCIBILITY_CAPSULE/x9r_smoke'))
"
python -m research.systemic_risk.protocol_x9r run \
    --dataset-dir REPRODUCIBILITY_CAPSULE/x9r_smoke/dataset_dir \
    --output REPRODUCIBILITY_CAPSULE/x9r_smoke/empirical_falsification_capsule \
    > REPRODUCIBILITY_CAPSULE/test_artefacts/X9R_RUN_actual.json 2>&1

# 5. Synthesise EXPECTED_OUTPUTS_actual.json from the artefacts
python - <<'PY'
import json
from pathlib import Path

root = Path("REPRODUCIBILITY_CAPSULE")
art = root / "test_artefacts"

x9r = json.loads((art / "X9R_RUN_actual.json").read_text())
out = {
    "x9r_verdict": x9r.get("verdict"),
    "x9r_max_claim_tier": x9r.get("max_claim_tier"),
    "x9r_failed_gate": x9r.get("failed_gate"),
    "x9r_tests_run": x9r.get("tests_run"),
}
(root / "EXPECTED_OUTPUTS_actual.json").write_text(
    json.dumps(out, indent=2, sort_keys=True), encoding="utf-8"
)
PY

echo "Capsule reproduction complete. Diff REPRODUCIBILITY_CAPSULE/EXPECTED_OUTPUTS_actual.json against REPRODUCIBILITY_CAPSULE/EXPECTED_OUTPUTS.json."
