# Phase 5 · Envelope stress

Block-bootstrap on the validated OOS log-return stream. Seed = 20260501
(distinct from live shadow seed 20260422 so the two views are
independent). Block length = 20 bars, 500 paths per horizon. CSV:
`envelope_stress.csv`.

## Summary

| horizon | median cumret | p05 | p95 | median max DD | p95 max DD | P(recover after early dip) |
|---:|---:|---:|---:|---:|---:|---:|
| 20 | +0.29 % | −7.59 % | +9.48 % | 3.75 % | 8.94 % | **5.65 %** |
| 40 | +1.45 % | −11.40 % | +14.54 % | 6.28 % | 14.07 % | **13.71 %** |
| 60 | +2.21 % | −12.63 % | +18.95 % | 7.71 % | 16.59 % | **12.80 %** |
| 90 | +3.63 % | −16.29 % | +21.82 % | 9.53 % | 20.86 % | **8.00 %** |

Breach frequencies at `p05` and `p25` are 0.05 / 0.25 by definition
(self-consistent sanity check).

## Key numbers

- **At the 90-bar truth gate**, median cumret = +3.63 %, p05 = −16.29 %. Matches shadow's "below_p05 ⇒ OUTSIDE_EXPECTATION" semantics.
- **Median max DD at 90 = 9.53 %, p95 = 20.86 %.** Both under the live 1.5× DD gate (25.14 %). Live max DD > ~21 % at 90 bars would be a ≥ p95 tail.
- **Recovery probability after early dip is low** at every horizon (5.6–13.7 %). A mid-horizon dip below p25 rarely climbs back to finish above the median.

## §ES6 answer

Rarely. Conditional recovery after a mid-horizon dip below p25 stays below 14 % at all four horizons. Implication for the shadow gate engine: sustained `below_p25` in the first half of the 90-bar window is a signal, not just a label — historical blocks rarely climb back. `UNDERWATCH` and `ESCALATE_REVIEW` semantics are appropriately pessimistic under this distribution.

**No gate parameters changed.** The stress view calibrates expectation, it does not alter the shadow rail.

## No-decision caveat

Descriptive. Block length 20, horizons 20/40/60/90, 500 paths, seed 20260501 were frozen in the protocol — no sweeps.
