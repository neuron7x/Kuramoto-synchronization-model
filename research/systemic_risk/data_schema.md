# DATA SCHEMA — research/systemic_risk

> Every field below is enforced at the boundary by
> `from_exposure_matrix`. Violation raises `ValueError` before any
> numerical computation runs (fail-closed).

## 1. Exposure matrix

| Field | Type | Constraint |
|-------|------|------------|
| `exposures` | `np.ndarray`, shape `(N, N)`, dtype convertible to `float64` | square 2-D; finite (no NaN/Inf); non-negative; `exposures[i, j]` is *i*'s exposure to *j* (i.e. lending **from** *i* **to** *j*); symmetric only by accident on real data, asymmetric in general. |
| `node_labels` | `tuple[str, ...]` | length `N`; unique; ASCII-stable identifiers; no remapping. |
| `directed` | `bool` | default `True`. `False` symmetrises by averaging — used only for null-baseline construction. |
| `threshold` | `float ≥ 0` | inclusive lower bound on a kept entry; entries strictly below `threshold` are clamped to zero in the binary support. |
| `snapshot_date` | `datetime.date` or `None` | optional; required for temporal-snapshot pipelines (e-MID quarterly, BIS LBS). |
| `source_label` | `str` | free-form provenance tag; recorded in the `RunManifest.extra` namespace as `dataset_source`. |

## 2. Spread series (for phase extraction)

| Field | Type | Constraint |
|-------|------|------------|
| `spreads` | `np.ndarray`, shape `(T, N_banks)`, `float64` | rows = time, columns = banks; finite. |
| `asset_ids` | `tuple[str, ...]` | length `N_banks`; unique. |
| `timestamps` | `np.ndarray`, shape `(T,)`, `float64` | monotonically increasing. |
| `fs` | `float > 0` | sampling rate in samples per day. |
| `band` | `(f_low, f_high)` cycles/day | `0 < f_low < f_high < fs/2`. |

## 3. Banking-crisis ledger

| Field | Type | Constraint |
|-------|------|------------|
| `country` | `str` | exactly 3 uppercase ASCII letters (ISO-3166 α-3). |
| `start` | `datetime.date` | first day of the crisis interval. |
| `end` | `datetime.date` | `≥ start`. |
| `source` | `Literal["LV2018", "LV2020_update", "post_LV2020"]` | provenance tag. |
| `label` | `str` | unique within the ledger. |

## 4. Run-manifest extra fields (recommended)

Callers persisting a run should populate `extra` with at minimum:

| Key | Value type | Purpose |
|-----|------------|---------|
| `dataset` | `str` | human-readable dataset identifier, e.g. `"e-MID_2009Q1-2015Q4"`. |
| `data_sha256` | `str` | SHA-256 of the canonical exposure-matrix file (sort_keys-serialised CSV/parquet). |
| `crisis_set` | `list[str]` | label set used for the falsification, e.g. `["GFC_USA_2007", "EZ_LATE_GRC_2011", "SVB_FRC_2023"]`. |

These are not enforced by the manifest itself — the protocol simply
refuses to promote any tier that does not produce them.

## 5. Forbidden inputs (fail-closed)

* Any `NaN` or `Inf` in `exposures`, `spreads`, or `timestamps`.
* Negative entries in `exposures` or `capital`.
* Zero or negative `fs`.
* `node_labels` with duplicates or empty strings.
* `T < 2` for `omega_from_volatility` (`std(ddof=1)` undefined).
* Mean degree `<k> < 2` for `fit_barabasi_albert`
  (BA-incompatible per Albert-Barabási 2002 eq. 4.7).
* Constant degree sequence for `fit_power_law` / `fit_barabasi_albert`
  (no fit possible).
