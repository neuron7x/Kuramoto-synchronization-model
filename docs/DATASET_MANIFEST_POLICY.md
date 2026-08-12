<!--
Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
SPDX-License-Identifier: MIT
-->
# Dataset Manifest Policy (DAT-001)

Immutable, checksum-pinned provenance for every canonical committed dataset, so
that **a result can cite an exact dataset digest** and **unknown or unlicensed
data fails closed (RED)**.

## Why

GeoSync is `RESEARCH_ALPHA` / `NO_DEPLOY` and **synthetic-only on its live
claims** (`governance/project_state.yaml`, `PRODUCT_CATEGORY.md`). A dataset
with no recorded source, no license, or no evidence class is an unaudited input
that can silently launder real market data into a "synthetic" result. This
policy makes each dataset input declare its provenance and makes the CI gate
refuse anything unknown or unlicensed.

## What is manifested (scope)

Scope is the **canonical committed dataset _inputs_** under `data/` plus a small
set of frozen fixtures — **not** the thousands of generated result artifacts
(`results/`, `experiments/**/results/`, `artifacts/`), which are *outputs*
derived from these inputs, not source datasets.

Each manifest lives at `data/manifests/<id>.json` and validates against
`schemas/dataset_manifest.schema.json`. One manifest describes one dataset and
lists its member files in `files[]` (each with its own sha256 + byte size).

| id | evidence_class | license | status |
|----|----------------|---------|--------|
| `sample-timeseries-v1` | SIMULATION | MIT | GREEN |
| `sample-ohlc-v1` | SIMULATION | MIT | GREEN |
| `sample-crypto-ohlcv-v1` | SIMULATION | MIT | GREEN |
| `sample-stocks-daily-v1` | SIMULATION | MIT | GREEN |
| `golden-macd-baseline-v1` | SIMULATION | MIT | GREEN |
| `frozen-kuramoto-trajectories-v1` | SIMULATION | MIT | GREEN |
| `binance-btcusdt-depth10-v1` | **MEASURED** | PUBLIC_NO_LICENSE | **RED / FLAGGED** |
| `askar-instruments-v1` | **MEASURED** | UNKNOWN | **RED / FLAGGED** |
| `askar-market-panel-v1` | **MEASURED** | UNKNOWN | **RED / FLAGGED** |

## Required fields

`id`, `source` (vendor + origin + retrieval_method + uri), `retrieval_time`,
`query`, `license`, `checksum` (sha256, dataset-level), `bytes`, `schema`,
`coverage` (row/time), `revision_status`, `access_restrictions`,
`evidence_class`, and `files[]`. Evidence classes are the closed governance
vocabulary: `{FACT, MEASURED, SIMULATION, HYPOTHESIS, RETIRED}`.

**Dataset-level checksum** = `sha256` over the sorted `"{path}  {file-sha256}"`
lines of `files[]` (`dataset_digest()` in the gate). A result references a
dataset by `id` + this digest.

## Fail-closed rules (the gate)

`scripts/ci/check_dataset_manifests.py` fails closed (exit 1, RED) when any
manifest:

1. violates `schemas/dataset_manifest.schema.json`;
2. declares a **non-granted license** — empty, `UNKNOWN`, `UNLICENSED`, `NONE`,
   `TBD`, `PUBLIC_NO_LICENSE` (redistribution rights not established);
3. declares an **unknown `evidence_class`**;
4. has a dataset-level `checksum.value` that does not match `dataset_digest(files)`;
5. has an **on-disk file whose recomputed sha256 or byte size differs** from the
   recorded value (tamper / drift).

Absent large binaries are reported but do not fail closed (the recorded digest
stands). Exit `2` is reserved for misconfiguration (missing schema / manifest
dir).

## Honesty finding — real data in a synthetic-only repo

Running the gate against the live repo is **expected to be RED**. Three
committed datasets are **real empirical market data**, which contradicts the
synthetic-only boundary and are unlicensed:

- **`data/askar/` + `data/askar_full/`** — real vendor OHLC for **53 named
  instruments** (SPDR S&P 500 ETF, XAUUSD gold, USA 500 Index, EURUSD, Euro
  Bund, iShares/VanEck ETFs, national equity indices), 2017-02-16 → 2026-02-23,
  up to ~57k hourly bars. **No license file, no recorded vendor agreement.**
- **`data/raw/binance_btcusdt_depth10.csv`** — real Binance USD-M futures L2
  depth (`data/l2_manifest.json`: `PUBLIC_NO_LICENSE`).

These are recorded as `evidence_class: MEASURED` (real data must **never** be
laundered as `SIMULATION`) and carry
`flags: ["REAL_DATA_CONTRADICTS_SYNTHETIC_ONLY_BOUNDARY", ...]`. The RED verdict
is the governance alarm, not a defect. **Resolution** requires governance /
SEC-015: either (a) establish and record a redistribution license and set
`license_verified: true`, or (b) remove the data from this synthetic-only
repository. This gate is intentionally **not** wired into `.gitlab-ci.yml` by
DAT-001; wiring it in should follow that governance decision.

## Relationship to SEC-015 (dependency cycle broken)

The register lists a DAT-001 ⇄ SEC-015 cycle. It is broken by role split: the
**manifest RECORDS** the license (`license`, `license_verified: false`); the
**SEC-015 license audit VERIFIES** it and flips `license_verified: true`. The
manifest therefore comes first.

## Adding or changing a dataset

1. Add the dataset under `data/`.
2. Add `data/manifests/<id>.json` with all required fields and per-file
   sha256/bytes; set the dataset-level checksum to `dataset_digest(files)`.
3. `FROZEN` datasets must never change bytes without a new `id`.
4. `python scripts/ci/check_dataset_manifests.py` must be reconciled (GREEN for
   synthetic/licensed data; a new real/unlicensed dataset is RED by design).
5. `python -m pytest tests/ci/test_dataset_manifests.py -q`.
