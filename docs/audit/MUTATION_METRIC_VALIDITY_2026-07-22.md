# What a mutation kill-rate can and cannot measure — five limits, each proven (2026-07-22)

Three calibration batches measured 19 claim modules. Seven read at or near **zero**. Investigating
every one of them — rather than "fixing" the number — separated **four genuine blind falsifiers**
(all now closed at 100%) from **three artefacts of the measurement method itself**. This document
is the resulting validity envelope for the metric.

## Final classification of the seven zeros

| module | reading | verdict after investigation |
|---|---|---|
| `session_fsm.py` | 0/1 | **GENUINE gap** — asserted the exception *type*, never its message → closed, **100%** |
| `serotonin_ode.py` | 0/6 | **GENUINE gap** — no test on the stability criterion at all → closed, **100%** |
| `dopamine_execution_adapter.py` | 0/3 | **GENUINE gap** — nothing asserted the returned value → closed, **100%** |
| `signal_bus.py` | 1/17 | **GENUINE gap** — nothing asserted which regime resulted → closed, **100%** |
| `sizing.py` | 0/26 | **ARTEFACT (limit 4)** — mis-paired; re-measured against its own tests: **88.5%** |
| `backtest.py` | 0/13 | **ARTEFACT (limit 5)** — determinism claim; falsifier sound (negative control) |
| `lint_forbidden_terms.py` | 0/4 | **ARTEFACT (limit 5)** — liveness claim; falsifier sound (negative control) |

**Genuine blind falsifiers: four. All four are now at 100% measured kill-rate.**

## The five limits

**1 — A test can pass and kill nothing.** `pytest.raises(ValueError)` also catches the ValueError
the *mutant itself* raises (a numpy broadcast error after inverting a shape guard), so the assertion
cannot discriminate. Fixed with `match=`. Separately, guards that feed only a **log** are invisible
to any numeric assertion; they need a `caplog` assertion against the module's stated observability
contract.

**2 — Module-level attribution under-reports a function-level claim.** `cpcv.py` reads 45.9%, but
16 of 20 survivors live in `cpcv_splits`/`estimate_pbo`, which the Newey–West HAC claim does not
assert. Padding those with tests would raise the number without strengthening the claim. A
module-level kill-rate is a **lower bound** on the falsifier's strength.

**3 — A survivor can be unkillable in principle (equivalent mutant).** Three `Or→And` guards in
`cpcv` were proven equivalent by loading the original and mutated modules side by side and comparing
outputs across inputs: byte-identical everywhere (6.0/6.0, nan/nan, nan/nan, 1.0/1.0). NaN
propagates; a Bartlett sum over `range(1, 0+1)` is empty.

**4 — A zero can be a pairing error.** When a claim declares several evidence modules but one
falsifier, pairing *any* module with *that* falsifier yields a spurious zero. `sizing.py` was paired
with a test that never imports it. **Check the pairing before reporting a zero.** Re-measured
correctly: 88.5%.

**5 — Some claims assert properties that are invariant under deterministic mutation.** Mutation
testing measures *behavioural discrimination*. A claim asserting **self-consistency / determinism**
(`run(x) == run(x)`) or **liveness / runnability** (`exit code == 0`) is invariant by construction:
mutate the logic and both runs change identically, so they stay equal; mutate the logic and the
script still exits 0. Kill-rate is therefore **not a valid strength metric for such claims** —
their strength must be measured by a **targeted negative control**: break exactly the mechanism the
claim asserts and require the falsifier to fire.

Both were verified that way, decisively:
- `backtest.py` — disabling `_reset_runtime_state()` (the rewind the claim asserts) made **two**
  tests fail.
- `lint_forbidden_terms.py` — forcing warn-mode to exit 3 made `test_forbidden_terms_lint_script_runs_warn_only` fail.

Both falsifiers are sound. Their 0% is a scope artefact, not a debt, and must not be "fixed".

## Operating rule this establishes
A low or zero kill-rate is a **question**, never a verdict. Before it may be called a teeth gap:
1. confirm the falsifier actually imports/exercises the module (limit 4);
2. confirm the survivors lie inside what the claim asserts (limit 2);
3. confirm the survivors are not equivalent mutants (limit 3);
4. confirm the claim's asserted property is behaviour-discriminating at all — if it asserts
   self-consistency or liveness, measure it with a negative control instead (limit 5);
5. and after writing teeth, **re-probe** — a passing test is not a killing test (limit 1).

Only what survives all five checks is debt. By that standard the debt was four modules, and it is
now zero.
