<!-- SPDX-License-Identifier: MIT -->
# Dependency Lock Policy (ENV-003)

**Gate:** `G-LOCK-HASHES` — `scripts/ci/check_lock_hashes.py`
**Artifact:** `artifacts/env/lock_provenance.json`
**Tests:** `tests/ci/test_lock_hashes.py`

## Contract

Every `requirements*.lock` in this repository MUST be **exactly pinned** and
**hash-locked** so that `pip install --require-hashes -r <lock>` is the only
admissible install path. A lock is admissible iff, for every requirement:

1. it is pinned with `==` (or PEP 440 `===`) to a single version — no `>=`,
   `~=`, `<`, `!=`, URL, or operator-less line survives;
2. it carries **at least one** well-formed `--hash=sha256:<64-hex>` entry;
3. no requirement name appears twice (canonicalised per PEP 503).

The only requirements exempt from the hash rule are the build-backend
distributions pip-tools leaves unpinned by default — `pip`, `setuptools`,
`wheel`, `distribute` (`ALLOW_UNHASHED_NAMES`). pip does not demand hashes for
these when they are already present in the environment. Any *other* unhashed
line is a **HARD, fail-closed** failure.

## Governed locks

| Lock | Source | Extras | Notes |
|------|--------|--------|-------|
| `requirements.lock` | `pyproject.toml` | runtime | `--no-strip-extras` |
| `requirements-dev.lock` | `pyproject.toml` (`--extra=dev`) | dev | `--no-strip-extras` + curated addendum (below) |
| `requirements-scan.lock` | `requirements-scan.txt` | scan | `--strip-extras`, constrained by `requirements.lock` |

## Reproducible regeneration (controlled)

Regeneration requires **pip-tools** and **network access to the index**. Run
from the repo root with a Python 3.12 interpreter:

```bash
# runtime lock (--allow-unsafe pins+hashes the backends, FUP-009)
pip-compile --generate-hashes --allow-unsafe --constraint=constraints/security.txt \
    --no-strip-extras --output-file=requirements.lock pyproject.toml

# dev lock (--allow-unsafe + see curated addendum note below)
pip-compile --generate-hashes --allow-unsafe --constraint=constraints/security.txt \
    --extra=dev --no-strip-extras --output-file=requirements-dev.lock pyproject.toml <curated-addendum.in>

# scan lock — constrained to the runtime lock so it can never drift below it;
# --allow-unsafe pins the backends, and the pip-audit scanner is a curated
# addendum (SEC-002, see docs/SCAN_TOOLCHAIN_POLICY.md)
pip-compile --generate-hashes --allow-unsafe --constraint=constraints/security.txt \
    --constraint=requirements.lock --no-annotate \
    --output-file=requirements-scan.lock --strip-extras requirements-scan.txt <scan-addendum.in>
```

Seed each output path with the current lock first (no-drift discipline) and pass
the curated pins (`POT`, `pytest-timeout` for the dev lock; `pip-audit==2.10.1`
for the scan lock) as an additional input file so they are retained and hashed;
then restore the documented header note.

### No-drift discipline

To **add hashes without upgrading versions**, seed the output path with the
current lock before running `pip-compile` (pip-compile preserves existing pins
it finds in the output file). Regenerating to a *fresh* path re-resolves to the
newest compatible versions and causes a full-tree upgrade — do **not** do that
under this task; version bumps are a separate, reviewed change. Every
regeneration MUST be accompanied by a reviewed resolver diff
(`git diff -- requirements*.lock`).

### Curated addendum (dev lock)

`pip-compile --extra=dev` does **not** emit two test-time dependencies that the
repo needs, so they are added as explicit inputs during regeneration and are
therefore hashed like everything else:

- **`POT` (`pot`)** — the `neuro_advanced` optional group provides the POT-backed
  Ollivier–Ricci kernel imported by
  `tests/research_lines/test_ricci_microstructure_v1.py`.
- **`pytest-timeout`** — consumed by the Makefile `l2-test` target
  (`--timeout=60`).

Both are declared in `requirements-dev.txt`; pin them to the versions already in
the dev lock and pass them as an additional input file when regenerating so they
resolve and receive `--hash` entries. Verify no other version drifts afterward.

## Build backends now pinned + hashed (FUP-009)

The locks are regenerated with **`--allow-unsafe`**, so pip-compile's "unsafe"
set (`setuptools`/`pip`/`wheel`) is now **pinned and hashed** wherever the
resolution actually pulls it — e.g. `setuptools==81.0.0` (pinned by
`constraints/security.txt`) enters the runtime lock via `ccxt`/`torch`. This
closes the ENV-003 gap where `pip install --require-hashes -r requirements.lock`
failed because `ccxt` pulled an unpinned `setuptools>=60.9.0`.

The `--allow-unsafe` flag is a **reviewable addition of new pinned lines**, not
a silent change: the resolver diff shows only the added backend blocks (plus
their hashes) and no existing package version moves. `pip` and `wheel` appear in
a lock only when that lock's dependency tree actually requires them (e.g. `pip`
enters the dev lock via `pip-tools`); the runtime lock only needs `setuptools`.

`check_lock_hashes.py` still exempts the backend names from the *mandatory*-hash
rule (`ALLOW_UNHASHED_NAMES`), but they are now hashed regardless, so the
`--require-hashes` install is fully self-contained.

## Verification (CI)

```bash
python -m scripts.ci.check_lock_hashes \
    --emit-provenance artifacts/env/lock_provenance.json
python -m pytest tests/ci/test_lock_hashes.py -q
```

The gate is **verify-only**: it never regenerates or mutates a lock. It reads
each lock's own pip-compile header to record the generating command in the
provenance artifact honestly, falling back to `verify-only` for any lock with no
generator provenance. A vacuous lock (fewer than `--min-requirements`
requirements) fails closed — a hash gate over an empty lock is not proof.
