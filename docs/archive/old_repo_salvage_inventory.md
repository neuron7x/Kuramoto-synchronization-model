# Old-Repo Salvage Inventory

**Status:** First-pass salvage audit, no runtime changes.
**Branch:** `audit/old-repo-salvage`
**New repo HEAD at audit time:** `e66946c`
**Old repo audited:** `Kuramoto-synchronization-model-main (2)` (snapshot under
`/home/neuro7/Downloads/`)
**Generated:** 2026-04-27

---

## Prime directive

> Save what contains a real mechanism, original intent, reproducible
> behaviour, product value, or IP provenance. Everything else becomes
> archive or rejection. Do not preserve nostalgia. Do not preserve
> overclaim. Do not delete old material because it looks obsolete.

This document is the human-readable companion to:

- `.claude/archive/OLD_REPO_SALVAGE_LEDGER.yaml` — machine-readable
  ledger (45 entries).
- `tools/archive/compare_old_repo_salvage.py` — fail-closed validator.
- `tests/archive/test_old_repo_salvage_ledger.py` — schema and
  round-trip tests (16 tests).
- `docs/archive/old_repo_only_files.txt` — full list of 430 paths
  that exist in the old repo but not in the new repo.

---

## File-level diff summary

| Metric                    | Count                      |
|---------------------------|----------------------------|
| Old repo files (.py/.md/.yaml/.yml/.toml) | 2700        |
| New repo files (same exts)               | 21527       |
| Only in old (raw)                        | 430         |
| Only in new (raw)                        | 19257       |

Most "only-in-old" paths are accounted for by **renames** (TradePulse →
GeoSync) rather than genuine losses. The audit separates the three
categories below.

---

## Salvage taxonomy

| Class            | Meaning                                                           |
|------------------|-------------------------------------------------------------------|
| `KEEP_NEW`       | Mechanism preserved under a renamed/relocated path.               |
| `PORT`           | Mechanism missing; restore the runtime artefact and its tests.    |
| `PORT_TESTS_ONLY`| Tests are unique; restore tests for surviving target modules.     |
| `ARCHIVE`        | Historical / IP / cross-domain artefact; preserve provenance only.|
| `QUARANTINE`     | Doc carries overclaims that must be neutralised in place.         |
| `REWRITE`        | Concept worth preserving but old impl is dirty/brand-bound.       |
| `REJECT`         | Obsolete infra, branding, or duplicate workflow.                  |

---

## Key findings (interpreted)

### 1. Most TradePulse-branded code is preserved as renames

| Old                                                   | New                                                  |
|-------------------------------------------------------|------------------------------------------------------|
| `analytics/regime/src/core/tradepulse_v21.py` (849)   | `analytics/regime/src/core/geosync_v21.py` (851)     |
| `analytics/regime/tests/test_tradepulse_v21.py` (263) | `analytics/regime/tests/test_geosync_v21.py` (265)   |
| `cli/tradepulse_cli.py` (1704)                        | `cli/geosync_cli.py` (1706)                          |
| `src/tradepulse/protocol/divconv.py`                  | `src/geosync/protocol/divconv.py`                    |
| `src/tradepulse/` (109 files)                         | `src/geosync/` (112 files)                           |
| `tradepulse/neural_controller/` (43)                  | `geosync/neural_controller/` (43)                    |
| `scripts/export_tradepulse_schema.py`                 | `scripts/export_geosync_schema.py`                   |
| `PRODUCT_PAIN_SOLUTION.md`                            | `docs/operations/PRODUCT_PAIN_SOLUTION.md` + `apps/risk_guardian/` |
| `SYSTEM_OPTIMIZATION_SUMMARY.md`                      | `docs/operations/SYSTEM_OPTIMIZATION_SUMMARY.md`     |
| `PHYSICS_IMPLEMENTATION_SUMMARY.md`                   | `docs/operations/PHYSICS_IMPLEMENTATION_SUMMARY.md`  |
| `PROJECT_DEVELOPMENT_STAGE.md`                        | `docs/operations/PROJECT_DEVELOPMENT_STAGE.md`       |

The `+2` LOC delta on the renamed code files is consistent with an SPDX
header insertion — mechanism preserved.

### 2. Genuinely missing — IP / provenance

- **`PATENTS.md`** (CRITICAL) — TACL invention disclosure with five
  formal claims, free-energy functional, monotonic descent constraint,
  LinkActivator hot-swap, RL crisis adaptation, 7-year audit trail.
  This is real IP provenance, not marketing. → **ARCHIVE** as
  `docs/ip/tacl_origin_disclosure.md` with explicit "NOT a granted
  patent" header.

### 3. Genuinely missing — cross-domain substrate

- **`configs/hbunified.yaml`** + **`hbunified.py`** +
  **`docs/hydrobrain_unified_v2.md`** (HIGH) — HydroBrain v2: an 8-station
  hydrology / flood / quality / physics substrate config (GNN+LSTM+
  Transformer, GB 3838-2002 quality target). Not part of the trading
  runtime, but encodes the user's earlier cross-domain thinking. →
  **ARCHIVE**, do not auto-import.

### 4. Genuinely missing — runtime / domain pieces

- **`docs/tradepulse_protocol.md`** — public spec for Div/Conv. Code
  survives in `src/geosync/protocol/divconv.py`; rebrand the spec.
- **`docs/api/clients/tradepulse_client.py`** — Python client SDK.
- **`docs/tradepulse_cli_reference.md`** — CLI ref doc.
- **`PERFORMANCE_REGRESSION_GUIDE.md`** — performance methodology.
- **`analytics/fpma/tradepulse_fpma/`**,
  **`markets/orderbook/tradepulse_orderbook/`**,
  **`core/neuro/adapters/tradepulse_adapter.py`** — domain packages.
- **`tradepulse/risk/`** (5), **`tradepulse/analytics/`** (2),
  **`src/tradepulse_agent/`** (5) — top-level subsystems separate from
  `src/tradepulse/`.
- **`neurotrade_pro/`** — standalone backtest/calibrate/validate runner
  (~12 files); only test references in the new repo.
- **`rust/tradepulse-accel/`** — Rust acceleration crate (3 files).

### 5. Legacy and obsolete

- **`legacy/`** — 10 files of pre-current scripts. ARCHIVE only.
- **`.github/workflows/`** — 61 old workflows. REJECT (new CI in place).
- **`deploy/helm/`** — 25 old Helm charts. REJECT until a new release
  needs them.
- **`tests/unit/`** — 43 old-only unit tests. PORT_TESTS_ONLY where the
  target module survives.

---

## Distribution of the 45 ledger entries

| Action            | Count |
|-------------------|------:|
| `KEEP_NEW`        |    14 |
| `PORT` / `PORT_TESTS_ONLY` |  3 |
| `REWRITE`         |    11 |
| `ARCHIVE`         |     9 |
| `QUARANTINE`      |     2 |
| `REJECT`          |     6 |

(Counts will drift as remediation PRs land.)

---

## Remediation queue

After this audit PR merges, one PR per salvage:

| PR    | Source                                            | Action      |
|-------|---------------------------------------------------|-------------|
| PR-S1 | `analytics/regime/src/core/tradepulse_v21.py`     | Confirm KEEP_NEW + add non-claim comment block. |
| PR-S2 | `analytics/regime/tests/test_tradepulse_v21.py`   | Confirm KEEP_NEW. |
| PR-S3 | `PRODUCT_PAIN_SOLUTION.md` + `apps/risk_guardian/`| Wire buyer-facing reproducibility evidence. |
| PR-S4 | `PATENTS.md`                                      | ARCHIVE → `docs/ip/tacl_origin_disclosure.md`. |
| PR-S5 | `SYSTEM_OPTIMIZATION_SUMMARY.md`                  | Cross-link to `NEURO_OPERATIONALIZATION_LEDGER`. |
| PR-S6 | `cli/tradepulse_cli.py` → `cli/geosync_cli.py`    | Confirm KEEP_NEW + restore CLI reference doc. |
| PR-S7 | `PHYSICS_IMPLEMENTATION_SUMMARY.md`               | QUARANTINE in place: add non-claim header. |
| PR-S8 | `configs/hbunified.yaml` + `hbunified.py` + `docs/hydrobrain_unified_v2.md` | ARCHIVE under `docs/archive/cross_domain_substrate_hbunified/`. |
| PR-S9 | `neurotrade_pro/`                                 | Audit and either fold into a runner wrapper or REJECT. |

---

## Local commands

```bash
# Validate the ledger.
python tools/archive/compare_old_repo_salvage.py

# Run the audit tests.
python -m pytest tests/archive/test_old_repo_salvage_ledger.py -v

# Static analysis.
python -m ruff check tools/archive tests/archive
python -m ruff format --check tools/archive tests/archive
python -m black --check tools/archive tests/archive
python -m mypy --strict tools/archive tests/archive
```

---

## Final law

> Save the mechanism, not the nostalgia.
