<!--
Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
SPDX-License-Identifier: MIT
-->
# Numerical Policy: No Silent Clamps (P0-5)

## Problem

Physics code routinely contains *clamp-shaped* operations: `max(lam_max, 0.0)`,
`+ 1e-12` epsilons on denominators, `np.clip(x, lo, hi)` saturations, implicit
`0.5 * (A + A.T)` symmetrisation, `np.abs(corr)` sign-loss, `np.nan_to_num`
repairs. None of these are wrong on their own. The danger is a **silent** clamp:
when the input leaves the physically admissible set, the clamp returns a
plausible number instead of failing or surfacing the repair. The invalid regime
then propagates as if it were healthy — exactly the class of defect that lets a
broken correlation matrix, a negative variance, or a super-luminal velocity pass
a downstream gate unnoticed.

## Policy

Every clamp-shaped operation in the scoped physics tree
(`core/kuramoto`, `core/physics`, `core/indicators`,
`core/config/kuramoto_ricci.py`) **must be declared** in the machine-readable
registry [`tools/physics/clamp_registry.yaml`](../../tools/physics/clamp_registry.yaml).
A declaration is a named clamp class binding each site (`path:line`) to six
mandatory fields:

| field | meaning |
| --- | --- |
| `name` | unique clamp-class identifier (equals the detected shape) |
| `reason` | why the clamp exists (engineering justification) |
| `physical_meaning` | what physical/statistical quantity it protects |
| `failure_mode` | the invalid regime it would otherwise hide, **and** how the `metadata_field`/test surfaces it instead of silencing it |
| `test_ref` | the test that fails if the clamp class becomes unbound |
| `metadata_field` | the observable (log / return field / asserted invariant) that records the repair so it is **not silent** |

The scanner [`tools/physics/check_silent_clamps.py`](../../tools/physics/check_silent_clamps.py)
is **fail-closed**: any clamp site in scope without a registry entry is reported
by name (`path:line`) and the process exits non-zero. Stale registrations (a
registered site that no longer contains a clamp) also fail, so the registry can
not drift away from the code.

### Detected clamp shapes

The scanner recognises a closed set of AST shapes, chosen to be precise enough
that legitimate non-clamp code is not flagged:

- `saturate_clip` — `np.clip` / `jnp.clip` / `ndarray.clip`
- `floor_maximum` — `np.maximum(x, lo)` (elementwise floor)
- `cap_minimum` — `np.minimum(x, hi)` (elementwise cap)
- `floor_builtin` / `cap_builtin` — `max(x, 0|eps)` / `min(x, 0|eps)`
- `epsilon_add` — `<expr> + 1e-k` (denominator / log / tolerance guard)
- `symmetrise` — `0.5 * (X + X.T)`
- `abs_sign_loss` — `abs(corr…)` on a signed correlation/coupling name
- `nan_repair` — `np.nan_to_num`

## Workflow for a new clamp

1. Add the clamp to physics code as usual.
2. Run `python tools/physics/check_silent_clamps.py` — it will flag the new
   `path:line` as **unregistered**.
3. Add the site under the matching clamp class in `clamp_registry.yaml`, or
   create a new class with all six fields, **truthfully** describing the
   failure mode it could hide and the observable that surfaces it.
4. Ensure a test exercises the boundary (the `test_ref`).
5. Re-run the scanner until it reports `PASS`.

## Relaxing the policy

If a clamp must be relaxed (e.g. a bound widened, an epsilon enlarged), the
reason is documented **in the registry entry itself** (the `reason` /
`failure_mode` fields), never only in a commit message. The registry is the
durable contract; commit messages are forgotten.

## Current surface

At the time of writing the scanner binds **172 clamp sites** across **8 clamp
classes** over the scoped physics tree, with **zero unregistered violations**.
The authoritative, always-current count is the scanner output and
[`docs/reports/numerical_clamp_policy.md`](../reports/numerical_clamp_policy.md).
