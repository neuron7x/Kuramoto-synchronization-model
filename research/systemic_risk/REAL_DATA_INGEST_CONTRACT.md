# Real-Data Ingest Contract — `interbank.panel.v1`

> Closes audit task T6 of the 9.9 upgrade. Frozen contract that the
> canonical-seven pipeline accepts as the **only** real-data shape.
> Any feed deviating from this contract is rejected by the
> `validate_real_data_contract()` validator before a single line of
> downstream code touches the panel.

This file is **immutable post-merge**. Schema bumps go through a
new file (e.g. `interbank.panel.v2`) and a versioned migration.

## 1. Required dataset directory

```
dataset_dir/
├── manifest.json                  # provenance + config
├── exposure_panel.parquet         # long-format (date, source, target, exposure)
├── node_mapping.parquet           # (node_id, bank_label) surjective onto 0..N-1
├── crisis_ledger.json             # {"events": [{"id", "date", "country"}]}
└── license.txt                    # plaintext licence; BLOCKED tokens trigger STOP
```

## 2. `manifest.json` — required fields

| Field | Type | Constraint |
|---|---|---|
| `source_id` | string | non-empty, non-whitespace |
| `schema_version` | string | must equal `interbank.panel.v1` |
| `capture_timestamp_utc` | ISO-8601 string | with explicit `+HH:MM` offset |
| `payload_sha256` | string | 64 lowercase hex; matches actual `exposure_panel.parquet` sha256 |
| `seed` | int | non-negative; root RNG seed |
| `config_hash` | string | sha256 of pre-registered config (sort_keys=True) |
| `n_banks` | int | ≥ 3 |
| `n_days` | int | ≥ 90 (≥ 3 × bootstrap min lead window) |
| `crisis_lock_timestamp_utc` | ISO-8601 string | < `first_evaluation_timestamp_utc` |
| `first_evaluation_timestamp_utc` | ISO-8601 string | with explicit offset |
| `config` | object (optional) | for leakage-sentinel scan |

## 3. `exposure_panel.parquet`

| Column | Dtype | Constraint |
|---|---|---|
| `date` | timestamp / date | strictly-increasing across snapshots |
| `source` | int | ∈ [0, n_banks); ≠ target |
| `target` | int | ∈ [0, n_banks); ≠ source |
| `exposure` | float64 | finite, ≥ 0 |

Diagonal entries (source == target) are forbidden.

## 4. `node_mapping.parquet`

| Column | Dtype | Constraint |
|---|---|---|
| `node_id` | int | surjective onto [0, n_banks) |
| `bank_label` | string | unique; survivorship-bias-aware, no duplicates |

## 5. `crisis_ledger.json`

```json
{
  "events": [
    {"id": "<unique>", "date": "<ISO-8601>", "country": "<ISO 3166-1>"}
  ]
}
```

* `id` unique within the file.
* `date` ≥ first panel date AND ≥ `first_evaluation_timestamp_utc`
  − 365 days. Events whose date falls inside the panel are
  rejected as **post-event contamination** by the leakage sentinel.

## 6. `license.txt`

Plaintext. The validator scans for any of:

```
BLOCKED, RESTRICTED, EXPIRED, DENIED, EMBARGOED
```

If any token appears, the contract returns **BLOCKED** (not FAIL).
The pipeline produces `verdict: BLOCKED_BY_DATA_ACCESS`.

## 7. Time-index semantics

* All times are UTC. Naive timestamps → reject.
* Dates in `exposure_panel` are date-only (no time-of-day).
* Lead-window for crisis `e_τ`: `[τ − L, τ)` (half-open, exclusive
  of crisis date).

## 8. Missingness policy

* No `NaN` allowed in `exposure_panel.exposure`.
* Missing exposures must be encoded as **omitted rows**, not `0.0`,
  unless the missingness is *structural* (no relationship between
  the two banks); in that case the dataset_dir's
  `manifest.json::config["missingness_policy"]` must equal one of
  `{"omit", "structural_zero"}`.

## 9. Bank-identity mapping

* `bank_label` is the canonical identifier. `node_id` is a
  zero-indexed renumbering inside this dataset. Cross-dataset
  identity requires a stable label, **never** the node_id.

## 10. Provenance hash format

* `payload_sha256` is computed via `sha256` over the binary bytes
  of `exposure_panel.parquet`, hex-encoded lowercase, exactly 64
  chars. The validator recomputes and rejects on mismatch.

## 11. Survivorship-bias policy

* The `bank_label` set must include **every** bank that existed in
  the time window, including those that subsequently failed,
  merged, or were acquired. Failed banks remain in `node_mapping`
  with `bank_label = "<original> (FAILED YYYY-MM-DD)"`.
* The validator emits **WARN** (not FAIL) on `bank_label`
  duplicates that look like merger artefacts (same prefix). Hard
  duplicates → FAIL.

## 12. Rejection conditions (any → FAIL)

* Missing required file or field
* Schema-version mismatch
* `payload_sha256` mismatch
* Naive timestamp (no timezone)
* Crisis lock ≥ first evaluation
* Negative or non-finite exposure
* Non-zero diagonal
* All-zero panel snapshot
* Non-surjective `node_id`
* Duplicate `bank_label`
* Crisis date inside panel
* Empty crisis ledger

## 13. Block conditions (→ BLOCKED, not FAIL)

* `license.txt` contains any of the blocked tokens
* `license.txt` empty (cannot establish licence) — alternatively
  treated as FAIL depending on the validator mode flag

## 14. Stub for downstream wiring

```python
from research.systemic_risk import validate_real_data_contract

report = validate_real_data_contract("/path/to/dataset_dir")
if report.status == "FAIL":
    raise RuntimeError(report.reason)
elif report.status == "BLOCKED":
    print("Cannot evaluate; respect the licence:", report.reason)
else:
    # status == "PASS"
    proceed_with_evaluation(report)
```

## Versioning

This is version **1.0** of the contract. Future bumps:

* `interbank.panel.v2` — when bilateral exposure is replaced or
  augmented with **secured-vs-unsecured** sub-channels.
* `interbank.panel.v3` — when panel is sub-sampled below the daily
  resolution.

Each version ships its own validator alongside this one; the
canonical-seven pipeline reads `manifest.json::schema_version` and
dispatches to the matching validator.
