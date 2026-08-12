# REPRODUCIBILITY — research/systemic_risk

> Per § 13 of the canonical R&D checklist, no result is accepted
> without the bundle below. Anything not yet implemented is
> flagged "PENDING" with the blocker named.

## Run-time provenance (manifest-bound)

| Field | Source | Status |
|-------|--------|--------|
| `commit_sha` | `replication.build_run_manifest` (`git rev-parse HEAD`) | ✓ on main |
| `git_dirty` | `replication.build_run_manifest` (`git status --porcelain`) | ✓ on main |
| `seed` (root) | caller-supplied; recorded verbatim | ✓ on main |
| `config` (full pre-registered dict) | caller-supplied; echoed | ✓ on main |
| `config_hash` (SHA-256, sort_keys) | `replication._config_hash` | ✓ on main |
| `python` (interpreter version) | `replication.build_run_manifest` | ✓ on main |
| `platform_info` (OS / arch) | `replication.build_run_manifest` | ✓ on main |
| `package_versions` (numpy, scipy, …) | `replication.build_run_manifest` | ✓ on main |

## Pipeline-execution artefacts

| Artefact | Status | Blocker |
|----------|--------|---------|
| Raw exposure panel data hash | PENDING | Real-data ingest not yet implemented |
| Per-snapshot adjacency hashes | PENDING | Same |
| Per-bank spread series hash | PENDING | Same |
| Score series file (CSV/parquet) | PENDING | Same |
| Per-crisis pre-event window slice | PENDING | Same |
| Null-baseline run reports (×6) | PENDING | `null_models.run_null_audit` deferred |
| Bonferroni-adjusted p-value table | PENDING | Same |
| Confusion-matrix metrics per crisis | PENDING | Real-data run |
| Lead-time aggregate report | PENDING | Real-data run |
| AUC bootstrap CI per crisis | PENDING | Real-data run |
| Sensitivity sweep table | PENDING | Real-data run |
| Plots (PNG + source `.npz`) | PENDING | Real-data run |
| `failed_tests.log` (hypothesis-shrunk) | PENDING | Real-data run |

`PENDING` does not mean "later" — it means **the absence of these
files prohibits any tier above `HYPOTHESIS / SCORE-LEVEL
INSTRUMENTATION EXTENSION`**.

## Determinism contract

* Every public function with stochastic content takes an explicit
  `seed: int`. No hidden global RNG.
* `np.random.default_rng(seed)` is the canonical entry; the
  legacy `np.random.RandomState` is forbidden.
* `replication.RunManifest.to_json()` is deterministic
  (`sort_keys=True`); two manifests built with identical inputs
  differ only on the timestamp line.

## Replication contract

A second run by an independent operator using only the
pre-registered config + the dataset SHA-256 must produce
**bit-identical** numerical outputs (modulo timestamps in the
manifest). Failure of this contract demotes any prior `MEASURED`
claim back to `HYPOTHESIS` automatically.
