# Data Governance Rules

This repository ships a small set of governed datasets under `data/`. Every dataset must declare provenance, be fingerprinted, and pass schema/semantic validation. CI blocks changes that violate these rules.

## Provenance & metadata

- Each `*.csv` in `data/` **must** ship a sidecar `*.meta.json` with:
  - `dataset_id`, `origin`, `description`, `creation_method`, `temporal_coverage`
  - `schema_version`, `intended_use`, `forbidden_use`
- Contracts live in `core/data/dataset_contracts.py` and are the source of truth for schema/semantic intent.
- Validate metadata:

```bash
python scripts/validate_datasets.py
# optionally emit fingerprints to artifacts
python scripts/validate_datasets.py --write-fingerprints artifacts/data-fingerprints
```

## Schema & semantics

- Schemas (columns + expected dtypes) are codified per dataset contract.
- Semantic checks enforced:
  - timestamps monotonic (`timestamp`/`ts` columns)
  - OHLC bounds: `low <= open/close <= high`
  - `volume` non-negative; no empty fields
- Validate schemas:

```bash
python scripts/validate_dataset_schema.py
```

## Fingerprinting & reproducibility

- `core/data/fingerprint.py` provides deterministic hashes:
  - `hash_csv_content`, `hash_schema`, `compute_dataset_fingerprint`
  - `record_run_fingerprint` writes JSON artifacts to `artifacts/data-fingerprints/`
- Backtest, calibration, and certification entrypoints emit fingerprints when a registered dataset is supplied:
  - `scripts/smoke_e2e.py` (backtest smoke)
  - `scripts/calibrate_controllers.py --dataset <csv>` (calibration provenance)
  - `scripts/serotonin_certify.py --dataset <csv>` (certification)

## Transformation traceability

- `record_transformation_trace` writes trace JSONs to `artifacts/data-traces/`.
- `core/data/preprocess.normalize_df(trace=True)` fingerprints input/output frames to guarantee non-mutation and auditability.

## Adding or modifying a dataset

1. Place the CSV under `data/` (or `data/golden/` for baselines).
2. Add a contract entry in `core/data/dataset_contracts.py`.
3. Add `*.meta.json` sidecar with provenance fields.
4. Bump `schema_version` if columns or semantics change.
5. Run:
   - `python scripts/validate_datasets.py --write-fingerprints artifacts/data-fingerprints`
   - `python scripts/validate_dataset_schema.py`
6. Commit updated artifacts directory placeholders if new subfolders are needed (do not commit generated fingerprints).

## CI gate

The `data-governance-validation` workflow runs the two validators and targeted data tests, uploading fingerprint/trace artifacts to help reviewers inspect dataset changes. Any missing metadata, schema drift, or semantic violation will fail CI.
