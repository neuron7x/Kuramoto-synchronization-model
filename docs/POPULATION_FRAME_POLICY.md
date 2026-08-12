<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Population / Sampling Frame Policy (FLAGSHIP-RQ-001)

**Task:** RES-006 · **Boundary:** `RESEARCH_ALPHA_SYNTHETIC_ONLY_NO_DEPLOY`
**Artifact:** `data/frames/flagship_population.json`
**Gate:** `scripts/ci/check_population_frame.py`
**Closure:** `tests/ci/test_population_frame.py`

This policy fixes the canonical *population* and *sampling frame* for the
flagship research question. A research claim is only as honest as the population
it is drawn from; this document and its manifest make that population explicit,
immutable, and reproducible.

## 1. Which population? (interpretation choice)

**Chosen interpretation: `infrastructure-modules` (NOT market datasets).**

FLAGSHIP-RQ-001 asks:

> *Does a clean-archive wheel-contract check surface latent first-party
> reproducibility defects that the pre-existing CI gate suite does not catch?*

It is explicitly an **infrastructure / synthetic-only** question over the
repository build artifact (`research/flagship/rq.yaml`: `domain_kind:
infrastructure`, `boundary: RESEARCH_ALPHA_SYNTHETIC_ONLY_NO_DEPLOY`). The RQ's
own preregistered `population` field reads: *"All first-party modules packaged
into the wheel ... plus every console_scripts entry point ... A finite,
enumerable repository artifact. No market data, no external universe, no
sampling."*

Therefore the **unit of analysis is a first-party Python module / import site**,
and the population is the set of such modules in the pinned repository snapshot —
**not** markets, instruments, or time series. Defining a market population over
the DAT-001 datasets (`askar`, `binance`) was **rejected as dishonest**: the RQ
neither samples nor makes any claim about market data, and doing so would import
a real-data / market-edge framing the question forbids.

## 2. The frame

| Element | Definition |
|---|---|
| **Unit** | One first-party Python module (its import site). |
| **Frame** | All git-tracked `*.py` whose top-level dir is a first-party *packaged* namespace at the pinned tree, after exclusions. |
| **Authoritative namespace set** | `[tool.setuptools.packages.find].include` in `pyproject.toml` — exactly what ships in the wheel the RQ interrogates. |
| **Frame size** | **1539** modules across **16** namespaces (`core`, `scripts`, `tools`, `src`, `geosync`, `analytics`, `application`, `execution`, `observability`, `geosync_pro`, `backtest`, `modules`, `libs`, `interfaces`, `domain`, `geosync_research`). |
| **Entry points** | The 12 `[project.scripts]` console entry points are part of the population (per the estimand) but are enumerated from packaging metadata by `check_wheel_contract.py`, not as `*.py` frame members. |

### Inclusion rules
1. git-tracked at the pinned commit;
2. path ends `.py`;
3. first path segment ∈ the packaged first-party namespace set.

### Exclusion rules (with counts at the pinned tree)
- **Tests** (`tests/…`) — 1898 excluded (packaging `exclude`; the RQ studies packaged modules, not the harness).
- **Docs** (`docs/…`) — packaging `exclude`.
- **Vendored / third-party** (`/vendor/`, `/vendored/`, `/third_party/`, `/_vendor/`) — 8 excluded (not first-party).
- **Generated** (`*_pb2.py`, `*_pb2_grpc.py`, `/generated/`, `/_generated/`) — 5 excluded (machine-emitted, not authored import sites).
- **Non-packaged first-party namespaces** (e.g. `agent`, `markets`, `sandbox`, `experiments`, `bench`, `apps`, …) — 650 excluded (not shipped in the wheel ⇒ outside the estimand).

### Missingness
No sampling, no imputation. The frame is a **complete census** of a finite,
enumerable artifact — there is no sampling missingness. A module that fails to
parse/import is an **outcome the RQ measures**, not a reason to drop it from the
frame. The digest is built from git blob SHAs, so it is independent of
working-tree state.

## 3. Pinned snapshot & immutable digest

- **Pinned commit:** `b012d3da99772b549d6b8a870596bd35b4d7601c` (resolves the RQ's `HEAD@wave3-p0` token).
- **Pinned tree:** `35b344a9327c798693623463b4dcc27db3331e52`.
- **Population digest (sha256):** `6c09f00747338aa92e681ae3099e1a231a9f2d9295894e4612e4e8c0d7a549be`.
- **Construction:** sha256 over sorted `"{path} {blobsha}\n"` lines of the frame members at the pinned tree.

The remediation commit that adds this manifest is a **descendant** of the pinned
commit, so the digest is computed over a frozen ancestor tree and stays
immutable as the branch advances. `check_population_frame.py --verify-digest`
(default on) **recomputes** the digest from the pinned commit and fails closed if
it does not reproduce — this is the reproducibility guarantee.

## 4. Target population & external validity (the honest boundary)

The claim generalizes to **this repository snapshot only** — commit `b012d3da`,
tree `35b344a9`. It makes **no** external-validity claim: not to other commits,
not to other repositories, and not to any market/live universe. The manifest
sets `generalizes_beyond_snapshot: false` and `external_validity_claim: null`;
the gate **flags and fails closed** on any boolean, field, or free-text
assertion of generalization beyond the snapshot. Redefining the frame (e.g. a
packaging-config change) requires a **new study id** per the RQ's
`scope_change_requires_new_study`.

### Recorded limitations
- **Snapshot-only** — frame/coverage/digest describe one commit; no external validity.
- **Synthetic-only / NO_DEPLOY** — modules/import sites, never market data; no alpha/edge/PnL claim.
- **Frame == packaging contract** — tied to `packages.find.include`; changing it needs a new study.
- **Marginal, not total** — supports counting defects surfaced *only* by the wheel contract, not total module quality.
- **No subsampling** — full census; no representativeness / sampling-error claims.

## 5. Collision with the dataset-manifest gate (DAT-001) — known, reported

`scripts/ci/check_dataset_manifests.py` (DAT-001) globs `data/manifests/*.json`
**non-recursively** and validates each against `schemas/dataset_manifest.schema.json`.
That schema is `additionalProperties: false`, requires 14 tabular-dataset fields,
and restricts `schema.format` to `csv/parquet/npz/npy/feather/arrow/json`. A
**module census is not a tabular dataset** and cannot be expressed under that
schema without lying about its nature. Consequently:

- `flagship_population.json` is a **`population_frame.v1`** document, validated by
  `check_population_frame.py` — **not** by the DAT-001 gate.
- Because it lands in the DAT-001 glob path (fixed by the RES-006 spec), the
  DAT-001 gate will emit a schema note for it. **This does not flip that gate's
  verdict:** DAT-001 is already, by design, RED on this repo (three unlicensed
  real datasets — `askar*`, `binance*` — are the documented governance alarm; see
  `docs/DATASET_MANIFEST_POLICY.md`). No green→red conversion is caused here.
- **Recommendation for the DAT-001 owner** (out of RES-006 scope; do not edit here):
  scope the DAT-001 glob to `manifest_version == "dataset_manifest.v1"` or relocate
  dataset manifests under `data/manifests/datasets/`, so frame manifests and
  dataset manifests are validated by their own gates.

## 6. How to verify

```bash
python scripts/ci/check_population_frame.py          # structure + digest reproduction
python -m pytest tests/ci/test_population_frame.py -q # positive + negative closure
python -m ruff check scripts/ci/check_population_frame.py tests/ci/test_population_frame.py
```
