# Physical Contracts — Why Tests Are Not Coverage Here

## The problem

Generic LLM-authored tests are *syntactic* supervision:
```python
assert 0 <= r <= 1    # bounds check — always true, always useless
assert kelly_fraction >= 0
```
They turn green, coverage climbs, and the system can still be physically
broken. The asserts never encoded any law of the system — they encoded the
shape of the function signature.

## What we want

Each test must be a **mathematical witness** of a specific physical law that
one of the 10 GeoSync core modules is obligated to obey. The witness derives
its numeric tolerance from the law's formula, not from a lucky round number.

```python
from physics_contracts import law

@law("kuramoto.subcritical_finite_size", N=1024, trials=200)
def test_r_scales_as_one_over_sqrt_N():
    r_samples = run_kuramoto(N=1024, K=0.5 * K_c, trials=200)
    # Tolerance is NOT 0.3 pulled from nowhere — it is 3/√N from the law.
    bound = 3.0 / math.sqrt(1024)
    assert np.mean(r_samples) < bound, (
        "kuramoto.subcritical_finite_size violated: "
        f"mean(r)={np.mean(r_samples):.4f} ≥ 3/√N={bound:.4f}"
    )
```

If anyone later changes `run_kuramoto` so it accidentally integrates above
K_c, the witness fails with a message that names the law, not a line number.

## The catalog

`catalog.yaml` lists every law as a first-class object with:

| field       | meaning                                                            |
|-------------|--------------------------------------------------------------------|
| `id`        | stable dotted identifier, e.g. `ricci.flow_monotonicity`           |
| `module`    | one of the 10 core modules                                         |
| `statement` | one-line human description                                         |
| `formula`   | mathematical expression                                            |
| `variables` | symbolic names and their meaning                                   |
| `tolerance` | how strict any witness must be (references `variables`)            |
| `validity`  | preconditions under which the law holds                            |
| `source`    | paper / ADR / docstring justifying the law                         |
| `severity`  | `block` = CI red on missing witness; `warn` = report-only          |

The initial catalog holds **27 laws** spanning Kuramoto (4), Ricci (2),
ECS/thermodynamics (4), Serotonin (2), Dopamine (2), GABA (2), Kelly (3),
OMS (3), SignalBus (2), HPC (2). Add more by appending to `catalog.yaml`
under `laws:` and running `tools/validate_tests.py`.

## The `@law` decorator

`physics_contracts.law(law_id, **kwargs)` binds a test function to a law by
id. At import time it:
1. Resolves the id against the catalog (unknown id → `KeyError` at
   collection → red build).
2. Records a witness in `WITNESS_REGISTRY` for the CI gate to audit.
3. Attaches the resolved `Law` object to the function as `__law__` so the
   body can read tolerances from the single source of truth.

The `**kwargs` are metadata that `tools/validate_tests.py` inspects — e.g.
`N=1024, trials=200` for a scaling witness — to verify that the declared
statistics actually match what the test code runs. This is how we stop the
obvious failure mode: `@law("…_scaling", trials=1000)` wrapping a test that
only runs 5 trials.

## The CI gate

`tools/validate_tests.py` runs in CI. It:

1. AST-walks every `tests/**/test_*.py` file.
2. For every test function, classifies it as
   **witness** (has `@law`), **migration-pending**, or **orphan**.
3. For witnesses, checks that:
   - the `law_id` resolves in `catalog.yaml`;
   - every numeric literal inside the function body either (a) is derived
     from a variable that came from the law, (b) is a dimensionless
     identity (0, 1, 2), or (c) has an inline `# law:` comment pointing at
     a `tolerance`/`variables` field of the law.
4. Emits a coverage report: how many laws have ≥ 1 witness, which blocking
   laws are missing.
5. Fails the build if any blocking law has zero witnesses or any witness
   references an unknown law id.

## Reading list for contributors

- `catalog.yaml` — the laws themselves.
- `law.py`      — the loader, registry, and `@law` decorator.
- `../tools/validate_tests.py` — the analyser and CI gate.
- `../BASELINE.md` — honest pre-contract baseline so you can measure drift.
