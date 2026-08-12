# GeoSync Physics Verification Runbook

> **Status:** canonical. The exact environment and commands to verify the
> physics layer from a fresh checkout. The audit found that physics gates have a
> non-obvious execution contract (`physics_contracts` is a standalone namespace;
> some gates need `PYTHONPATH=.` or an editable install). This runbook removes
> that ambiguity.

## 1. Environment

`physics_contracts` is **not** in the wheel's `packages.find` include list; it is
imported from the repository root. Run physics verification from an editable
install so both `physics_contracts` and the optional runtime deps resolve.

```bash
# from the repository root
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
```

If you only need the zero-dependency gates (claim boundary, invariant count,
docs canon), `PYTHONPATH=.` is sufficient without an install:

```bash
export PYTHONPATH=.
```

## 2. PYTHONPATH policy

- Editable install (`pip install -e .`) — preferred; no `PYTHONPATH` needed.
- Otherwise export `PYTHONPATH=.` from the repo root so `physics_contracts.*`
  and `core.*` resolve.
- Never run physics scripts from a subdirectory without one of the above; a bare
  `python scripts/ci/...` from a clean tree raises `ModuleNotFoundError:
  physics_contracts`.

## 3. Local verification (fast, zero/low dependency)

```bash
export PYTHONPATH=.
python scripts/count_invariants.py                       # must print 112
python scripts/ci/check_physics_docs_canon.py            # manifest + canon docs
python scripts/ci/check_claim_boundary.py                # product-category firewall
python scripts/ci/check_docs_consistency.py              # docs canonical-root gate
```

## 4. Full verification (installed environment)

```bash
python -m pip install -e ".[dev]"
python scripts/ci/check_invariant_source_binding.py      # invariant ↔ source/test binding
python scripts/ci/check_physics_law_witness_index.py     # law → witness index
python scripts/ci/check_physics_inference_readiness.py   # inference readiness gate
pytest -q tests/unit/physics tests/physics_contracts tests/physics
```

## 5. Regenerating the canon manifest

When a law or invariant is added/removed/renamed, regenerate and commit:

```bash
python scripts/ci/check_physics_docs_canon.py --write
git add docs/PHYSICS_CANON.manifest.json
```

The default-mode gate then fails closed until the manifest matches the
substrates, so a new physics surface cannot land unclassified.

## 6. Acceptance

A fresh checkout that follows §1 can run §3 and §4 with no undocumented
environment assumptions. Any `ModuleNotFoundError` means an environment step in
§1–§2 was skipped, not that a gate is broken.
