# Closing the measured teeth gaps: three falsifiers made able to fail (2026-07-22)

The calibration pass measured four claim falsifiers and recorded three surviving mutants —
behaviour changes the falsifiers could not detect. This closes all three. Every claim is
re-measured with the same procedure (`tools/mutation_probe.py --only-logic`, serial, tree-restore
verified), so the improvement is a measurement, not an assertion.

| claim / module | before | after |
|---|---|---|
| hpc-session-lifecycle-explicit-fsm — `session_fsm.py` | **0.0%** (0/1) | **100.0%** (1/1) |
| hpc-fixed-point-ledger-conservation — `ledger.py` | 90.9% (10/11) | **100.0%** (11/11) |
| hpc-indexed-rng-control-flow-free — `indexed_rng.py` | 88.9% (8/9) | **100.0%** (9/9) |
| hpc-runtime-state-envelope-integrity — `runtime_state.py` | 100.0% (5/5) | 100.0% (5/5) |

## What each survivor actually was — and why no test saw it

**1. `session_fsm.py:145` `Eq → NotEq` (the whole falsifier had ZERO teeth).**
`allowed = [a for (s, a) in TRANSITIONS if s == self.state]` feeds only the *hint* inside
`InvalidTransitionError`. Every existing test asserted the exception **type**
(`pytest.raises(InvalidTransitionError)`) and never its message, so flipping the filter — which
makes the hint list the actions admissible from every **other** state, i.e. actively misleads the
operator — was invisible. The new test derives the expected list **independently in test code**
and compares it to the message, so an inverted comparison in the source can no longer agree with
it.

**2. `ledger.py:295` `Or → And`.**
`if fill_price_scaled <= 0 or mark_price_scaled <= 0: return False` is a fail-closed price guard.
Under `and` it only fires when **both** prices are non-positive, so a single invalid price slips
through and the function computes on garbage instead of refusing. No test exercised the one-sided
case; the new test asserts both one-sided cases return `False`.

**3. `indexed_rng.py:152` `Lt → GtE`.**
`bernoulli` is `uniform(...) < p`. Nothing pinned the direction, so an inverted coin (fires exactly
when it should not) was undetectable. The new test pins the degenerate boundaries: `p=0.0` must
never fire and `p=1.0` must always fire over 64 indices — both flip under the mutant.

## Why this matters beyond three tests
Each gap was a test that **could not fail** guarding a claim the categorical audit reported as
`SUPPORTED`. The weighting layer surfaced them as measured zeros/partials rather than letting a
green wall stand. All four claim modules now measure 100% logic-mutation kill-rate; the manifest
aggregate moves 70/140 → **73/140 (52.14%)** and the mutation-kill ratchet held.

## Residual (stated)
Coverage is still 4 of 22 SUPPORTED claims. The remaining 18 carry no measured falsification power,
so the system-level tier stays `EXTRAPOLATED` — extending measurement to those modules is the next
increment, and until it happens the artifact reports the honest number.
