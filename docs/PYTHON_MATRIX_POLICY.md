# Python Version Matrix Policy (ENV-002)

Companion to **ENV-001** (the canonical Python **3.12** environment preflight,
`scripts/ci/check_env_preflight.py` + `artifacts/env/python312.json`).

## Declared support window

GeoSync declares a two-leg support window in `pyproject.toml`:

```toml
requires-python = ">=3.11,<3.13"
classifiers = [
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
```

So **3.11 is a first-class, declared supported version** — not an aspiration.
ENV-002 exists to give the 3.11 leg the same enforced dependency policy as the
3.12 leg and to detect version-specific divergence between the two.

## What ENV-002 delivers

| Artifact | Role |
| --- | --- |
| `artifacts/env/python311.json` | The 3.11 environment **CONTRACT** — target interpreter minor, the same 46 required dependencies, the same floors/specifiers as the canonical dependency policy. |
| `scripts/ci/check_py_matrix.py` | The **matrix gate** — a pure, fail-closed policy checker that validates a matrix-leg contract against `requirements.txt` (dependency set + floors) and the `pyproject.toml` support window (declared legs). |
| `tests/ci/test_py_matrix.py` | Closure: positive (the 3.11 contract validates → exit 0) + negatives (target 3.9, missing dep, extra dep, floor divergence, downgraded pandas floor, out-of-policy resolved version → non-zero). |
| `.github/workflows/python-matrix.yml` | The **live matrix CI** — runs the full suite on **both** 3.11 and 3.12, and runs the contract gate. |

## Contract vs. live run — the honest boundary

`artifacts/env/python311.json` is a **CONTRACT**, not a live environment
snapshot. It is explicitly marked:

```json
"kind": "contract",
"resolution_status": "pending-matrix-ci",
"required_dependencies": { "resolved": { "<dep>": null, ... } }
```

Every per-dependency `resolved` version is `null`. This is deliberate: the
authoring environment for ENV-002 had **only a Python 3.12 interpreter**, so a
live 3.11 resolution could not be honestly emitted there. Fabricating 3.11
resolved versions from a 3.12 interpreter would be a false witness.

**The live 3.11 build / import / full-suite / artifact-generation happens in the
matrix CI**, specifically the `live-suite (py3.11)` leg of
`.github/workflows/python-matrix.yml`. That leg builds the 3.11 venv, imports
`core`, runs the full test suite, and emits a genuine live 3.11 descriptor
(`artifacts/env/live-py3.11.json`) as a build artifact. A fully hermetic,
reproducible image is **ENV-005**'s scope; ENV-002 is the pre-hermetic matrix
proof.

## The gate contract (fail-closed)

`check_py_matrix.py::evaluate_contract` is a pure function over a descriptor
dict. It fails closed (exit 1) on any of:

- **Unsupported target** — declared target minor not in the `pyproject.toml`
  classifier legs (e.g. a descriptor claiming 3.9 or 3.13).
- **Missing required dependency** — a name in `requirements.txt` absent from the
  contract.
- **Extra dependency** — the contract declares a dep that is not a requirement.
- **Specifier divergence** — a contract floor/specifier that differs from
  `requirements.txt` (catches a version-specific policy fork between legs).
- **Floor mismatch** — recorded `python_floor` / `pandas_floor` inconsistent
  with policy.
- **Out-of-policy resolved version** — *only checked when a live leg has actually
  filled `resolved`* — a resolved version that violates its own floor.

The contract is generated **from** `requirements.txt`
(`check_py_matrix.py --emit-contract`), so it cannot silently drift: the CI
`contract-gate` job rebuilds it and asserts byte-for-byte equality with the
committed file.

## Acceptance

- Build / import / full-suite / artifact-generation on 3.11: **deferred to the
  `live-suite (py3.11)` matrix-CI leg** (not runnable in the 3.12 authoring
  sandbox; see boundary above). No supported-version reduction is recorded —
  3.11 remains a declared supported leg.
- Contract + matrix gate + closure tests: **green in the authoring sandbox**
  (`pytest tests/ci/test_py_matrix.py`, `check_py_matrix.py`, `ruff check`).

## Running locally

```bash
# Validate the committed 3.11 contract against policy:
python scripts/ci/check_py_matrix.py --contract artifacts/env/python311.json

# Rebuild the contract from policy (should reproduce the committed file):
python scripts/ci/check_py_matrix.py --emit-contract artifacts/env/python311.json --target 3.11

# Closure tests:
python -m pytest tests/ci/test_py_matrix.py -q
```
