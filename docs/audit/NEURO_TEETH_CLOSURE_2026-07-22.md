# Neuro-stack teeth closure — two P0 modules from zero to full measured power (2026-07-22)

Batch 2 measured three P0 neuro modules at ~zero logic-falsification power while the categorical
audit verdicted their claims SUPPORTED. This closes two of them completely and raises the third,
each move proven by re-running the same probe rather than asserted.

| module | before | after | remaining survivors |
|---|---|---|---|
| `core/neuro/serotonin_ode.py` | **0.0%** (0/6) | **100.0%** (6/6) | 0 |
| `core/neuro/dopamine_execution_adapter.py` | **0.0%** (0/3) | **100.0%** (3/3) | 0 |
| `core/neuro/signal_bus.py` | 5.9% (1/17) | **23.5%** (4/17) | 13 |

## What was blind, and what now pins it

**`serotonin_ode.py` — the Lyapunov certificate had no test at all.** Six mutants survived,
including comparison flips *inside the stability criterion itself* (`:176 NotEq→Eq` on the
target/baseline precondition, `:179 LtE→Gt` on the decay-sum guard, `:181 Gt→LtE` on
`a·2λμ > (δ/2)²`), plus `:209/:216` in the trajectory check and `:64 Or→And` swallowing
caller-supplied parameters. The new tests assert the certificate is True for defaults (which alone
kills all three certificate inversions, since each would flip that answer), then pin each refusal
branch separately (target≠baseline, non-positive decay sum, violated criterion), reject an
*increasing* V trajectory, and assert explicit params are honoured rather than silently replaced.

**`dopamine_execution_adapter.py` — nothing asserted `compute_sharpe_delta`'s value.** All three
guards were invertible. The new test computes Sharpe(recent) − Sharpe(previous) independently in
test code and requires equality, which simultaneously kills the insufficient-data inversion (would
force 0.0), the empty-segment inversion (would force 0.0) and the zero-variance inversion (would
divide by the 1e-12 floor and explode).

**`signal_bus.py` — the Protector veto was fully invertible.** `should_hold()` implements the
unconditional Protector priority (CLAUDE.md §0, INV-YV1 L2), yet `:238` (serotonin threshold),
`:240` (crisis check) and `:241` (their OR-join) could all flip undetected. The new truth table
pins: the serotonin veto fires alone, the threshold is strict (at-threshold does not veto), neither
firing means no veto, and a firing Protector **zeroes** the position multiplier rather than damping
it.

## Residual (stated)
`signal_bus.py` retains **13 survivors** — two in `compute_position_multiplier` (the piecewise
coherence bounds `:281/:283`) and eleven in `_update_regime` (`:345–:382`). Those need regime-
transition and coherence-interpolation boundary tests and are the next increment. Manifest
aggregate moves 129/247 → **141/247 (57.09%)**; ratchet held.
