# Reproduction Steps (≤ 10 minutes)

```bash
git clone https://github.com/neuron7xLab/GeoSync.git
cd GeoSync
git checkout v0.9.9-research-integrity-candidate   # or the SHA in the capsule
python -m pip install -r requirements.txt
```

## 1. Smoke run — Protocol X-9R on synthetic data

```bash
python -c "
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('h', 'tests/research/systemic_risk/test_protocol_x9r.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
mod._build_clean_dataset(Path('/tmp/x9r'))
"
python -m research.systemic_risk.protocol_x9r run \
    --dataset-dir /tmp/x9r/dataset_dir \
    --output /tmp/x9r/empirical_falsification_capsule
```

**Expected output:**

```json
{
  "verdict": "PASS",
  "max_claim_tier": "OBSERVED_IN_DATASET",
  "failed_gate": null,
  "tests_run": 9
}
```

## 2. Capsule rerun

```bash
bash /tmp/x9r/empirical_falsification_capsule/rerun.sh
```

Should print the same `verdict: PASS`. Tampering with
`capsule.json::metrics_sha` and re-running the rerun must produce
`verdict: FAIL` with `failed_gate: RERUN_CHECK` and
`max_claim_tier: REJECTED`.

## 3. Full test suite

```bash
python -m pytest tests/research/systemic_risk/ -q
python -m pytest tests/metamorphic/ -q
python -m pytest tests/negative_controls/ -q
```

Expected: **562 + 25 + 17 = 604 passing, 0 failing.**

## 4. Static analysis

```bash
python -m mypy --strict research/systemic_risk/ tools/
python -m ruff check research/systemic_risk/ tools/ tests/
python -m black --check research/systemic_risk/ tools/ tests/
```

Expected: zero diagnostics.

## 5. Research-integrity gate

```bash
python tools/check_public_symbol_matrix.py
python tools/compile_claims.py --fail-on-floating
```

Expected: both return PASS with non-zero rows / claims.
