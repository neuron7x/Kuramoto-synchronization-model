# ENV-009 — Environment Preflight Policy

**Status:** active
**Gate:** `scripts/ci/preflight_environment.py`
**Tests:** `tests/ci/test_preflight_environment.py`
**Gatekeeper for:** TST-001 (the test suite)

## Purpose

ENV-009 is the **fail-closed environment guard that runs BEFORE any gate or the
test suite**. If the environment is wrong, the suite never starts, and the
caller learns *which class* of fault stopped it from a **class-specific,
non-zero exit code**. A correct environment is the only path to exit `0`.

This is deliberately broader than **ENV-001** (`check_env_preflight.py`), which
answers a narrow "is this the canonical 3.12 interpreter with resolvable deps"
question and emits `artifacts/env/python312.json`. ENV-009 is the ordered
pre-suite guard: version range, key dependency floors, architecture, locale,
timezone, required binaries, free disk/memory, and forbidden editable installs.

## Design contract

- The verdict lives in one **pure function**, `evaluate(env_facts, requirements)`,
  over plain dicts. It reads nothing from the real interpreter, filesystem, or
  process table, so **every failure class is simulated by injecting a doctored
  `env_facts`** — no need to uninstall pandas or downgrade Python to test the
  gate.
- `probe_env_facts()` is the only impure half: it reads the live interpreter,
  installed-distribution metadata, `PATH`, disk/memory, and editable-install
  descriptors into the same dict shape tests inject.
- **Fail-closed:** any HARD failure yields a non-zero exit code specific to the
  failure class. When several HARD classes fail at once, the exit code is the
  **lowest** code among them (the earliest, most fundamental class), so the
  reported code is deterministic regardless of probe order.

## Checks implemented

| Check | HARD / advisory | Source of truth |
|-------|-----------------|-----------------|
| Python version in supported range `>=3.11,<3.13` | HARD | `pyproject.toml` `requires-python` |
| pandas present and `>= 2.3.3` | HARD | named gatekeeper floor |
| Required deps present (`aiolimiter`, `tenacity`, `numpy`), floor where given | HARD | `pyproject.toml` dependencies |
| CPU architecture in supported set (`x86_64`/`amd64`/`aarch64`/`arm64`) | HARD | `platform.machine()` |
| Preferred locale encoding is UTF-8 | HARD | `locale.getpreferredencoding()` |
| Timezone resolvable | HARD | `time.tzname` / `TZ` |
| Required binaries on `PATH` (`git`; optional: `docker`, `make`, `gh`) | HARD (required) | `shutil.which` |
| No forbidden editable install of the package outside the repo | HARD | PEP 610 `direct_url.json` |
| Free disk above advisory floor | **advisory** | `shutil.disk_usage` |
| Free memory above advisory floor | **advisory** | `os.sysconf` |

## Exit-code map

| Code | Class | Meaning |
|------|-------|---------|
| `0`  | PASS | environment satisfies every HARD invariant |
| `10` | `PYTHON_RANGE` | interpreter outside supported `[3.11, 3.13)` range |
| `11` | `PANDAS_FLOOR` | pandas missing or below the `2.3.3` floor |
| `12` | `MISSING_DEPENDENCY` | a required dependency absent (or below floor) |
| `13` | `ARCHITECTURE` | CPU architecture not in the supported set |
| `14` | `LOCALE` | preferred encoding is not UTF-8 |
| `15` | `TIMEZONE` | no timezone resolvable |
| `16` | `MISSING_BINARY` | a required binary (e.g. `git`) not on `PATH` |
| `17` | `FORBIDDEN_EDITABLE` | rogue editable install of the package points outside the repo |
| `20` | `DISK` | *(advisory)* free disk below the advisory floor |
| `21` | `MEMORY` | *(advisory)* free memory below the advisory floor |

Advisory classes are **reported but never change the exit code** in a sandbox.

## Forbidden editable installs

A `pip install -e` of the package (`geosync`) is *legitimate* only when it
targets this worktree's toplevel **or** the canonical repo that owns the shared
`.git` (a `git worktree` shares one common dir). An editable whose target is
outside every allowed repo root is a **rogue install** (see the
`rogue-editable` incident: alien code executing from a stray editable checkout)
and fails closed with code `17`.

## Usage

```bash
# Run BEFORE the suite; a non-zero exit means: do not start pytest.
python scripts/ci/preflight_environment.py            # human-readable
python scripts/ci/preflight_environment.py --json     # machine-readable report
```

Typical CI wiring:

```bash
python scripts/ci/preflight_environment.py || exit $?   # class-specific code
python -m pytest ...                                     # only reached on PASS
```

## Residuals / honest boundaries

- **Disk/memory thresholds are advisory in a sandbox.** They are measured and
  reported (codes `20`/`21`) but do not fail the gate, because a CI sandbox may
  legitimately run tight on both. Promoting them to HARD is a policy decision
  for a dedicated hermetic runner, not this descriptor gate.
- **Dependency floors beyond pandas.** Only `pandas` carries a hard version
  floor here; `numpy`/`aiolimiter`/`tenacity` are checked for **presence** (a
  floor is honored if supplied via `requirements`). The full below-floor audit
  belongs to ENV-001/ENV-005, not this pre-suite guard.
- **Timezone/locale** verify *resolvability and UTF-8*, not a specific
  canonical zone; the suite is timezone-agnostic beyond needing one to exist.
