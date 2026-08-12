# B.wheel-Zero Packaging Contract

**Goal:** the distributable `geosync` wheel ships only canonical `geosync*`
packages, with **zero** packaged-module imports of unpackaged first-party
namespaces and **zero** dead console scripts — proven by a clean isolated wheel
build + install, not asserted.

This is fail-closed and monotone: the legacy surface may only shrink.

## Current baseline (measured, not claimed)

Reproduce:

```bash
python scripts/ci/check_wheel_contract.py --no-dynamic   # ratchet verdict + artifacts/wheel_contract.json
python scripts/ci/check_wheel_contract.py --strict       # post-migration TARGET verdict (currently FAIL)
```

| Metric | Value | Source |
|---|---|---|
| non-`geosync` packages in wheel | **13** | `artifacts/wheel_contract.json::non_geosync_packages` |
| latent broken imports (packaged module → unpackaged first-party) | **70** | `::import_failures` |
| dead console scripts | **0** | `::script_failures` |
| ratchet verdict (debt frozen) | **PASS** | `--no-dynamic` |
| strict / target verdict | **FAIL** | `--strict` |

The 70 latent imports are real pre-existing debt — e.g. the *packaged*
`src/geosync/sdk/mlsdm/facade.py` imports unpackaged `rl` and `runtime`;
`scripts/*` and `tools/*` import unpackaged `research`, `governance`,
`instrument_validation`, `physics_contracts`. A clean-venv install of those
modules would `ModuleNotFoundError`.

## Gates

- **`scripts/ci/check_wheel_contract.py`** (WP-01) — builds the wheel from a
  clean `git archive HEAD` (immune to stale `build/` and pip cache), then
  enforces: (1) every `[project.scripts]` target package is shipped, (2) no
  packaged module imports an unpackaged first-party namespace, (3) `import
  geosync` + entry-point import smoke in a fresh `--no-deps` venv (third-party
  misses are `NEEDS_EXTRA`, not contract breaks). Emits
  `artifacts/wheel_contract.json`.
- **`.github/bwheel_baseline.json`** (WP-02) — the transitional ledger:
  `allowed_legacy_packages` (with per-package justification) + `import_debt`.
  Both sets may **only shrink**. `check_wheel_contract.py` fails on any NEW
  legacy package or NEW import-debt entry, and on a stale baseline after paydown
  (tighten with `--write`).
- **`scripts/ci/check_package_boundary.py`** — the narrower package-count
  predecessor (still active); `check_wheel_contract.py` supersedes it for the
  full contract.

## Transitional exceptions (allowed_legacy_packages)

Each legacy package remains only because an installed entry point or a packaged
import still resolves into it. Removal is sequenced in ADR-0024:

| Package | Why still shipped | Removal step |
|---|---|---|
| `application` | `geosync-server` entrypoint | WP-05 re-home → `geosync.runtime.server` |
| `core` | `tp-kuramoto` entrypoint + heavy import graph | WP-04 re-home → `geosync.kuramoto.cli` |
| `tools` | `geosync-research` entrypoint + docs tooling | WP-03/WP-06 |
| `scripts` | `geosync-scripts` + 5 dev entrypoints | WP-06/owner decision |
| `src` | `setuptools_scm.version_file = src/_version.py` + stale fork | version_file relocation + import-arch ratchet |
| others (`analytics`, `backtest`, `domain`, `execution`, `interfaces`, `libs`, `modules`, `observability`) | imported by the entrypoint-anchored packages above | drop after their importers re-home |

## How to tighten the ledger

After a re-home removes a package or fixes an import:

```bash
python scripts/ci/check_wheel_contract.py            # fails: baseline stale
python scripts/ci/check_wheel_contract.py --write    # tighten (only shrinks)
git add .github/bwheel_baseline.json
```

## Forbidden shortcuts

- Cosmetic package shaving (e.g. dropping `cli` while `tools/docs` still imports
  it) — creates a latent broken import; the gate fails on it.
- Excluding a package while any installed entry point or packaged import needs it.
- Claiming `B.wheel=0` without `--strict` verdict `PASS` and an empty
  `allowed_legacy_packages` + `import_debt`.
- Treating a local green as merge-ready: **CI is the oracle.**

## Definition of done (B.wheel = 0)

`python scripts/ci/check_wheel_contract.py --strict` returns `PASS`:
`import geosync` works, every console script smoke-runs, no packaged module
imports an unpackaged namespace, and the wheel ships only `geosync*`.
