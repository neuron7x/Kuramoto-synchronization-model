# 48h Staging Report

This report captures a 48 hour flash-crash replay with order-flow toxicity (VPIN) above
0.8 during the stress window. The scenario validates the thermodynamic control loop
and protocol activator safety behaviour in a representative pre-production soak.

## VPIN Toxicity
- Steps simulated: 48
- Mean VPIN: 0.625
- Peak VPIN: 0.869

## Thermodynamic Response
- RL actions observed: 0
- RL action changes: 0 (rate 0.000)
- RL policy stable: yes
- Monotonic invariant violations: 0

### Free Energy Trace
| Step | F(t) |
| --- | --- |
| 0 | -0.000000 |
| 4 | -0.000000 |
| 8 | -0.000000 |
| 12 | -0.000000 |
| 16 | 0.000000 |
| 20 | 0.000000 |
| 24 | 0.000000 |
| 28 | 0.000000 |
| 32 | 0.000000 |
| 36 | 0.000000 |
| 40 | 0.000000 |
| 44 | 0.000000 |
| 47 | 0.000000 |

### Crisis Timeline
- CRITICAL mode entered at steps: 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47
- Manual override was not required.
- Circuit breaker active: yes

## Synthetic Tail Metrics (Internal Benchmark)
- Tail free-energy mean (95% internal): 0.000000
- Internal tail budget met: yes

## Link Activator Stability
- Protocol traces:
  - ingest->matcher:hydrogen: grpc × 48
  - matcher->risk:hydrogen: grpc × 48
  - risk->broker:hydrogen: grpc × 48
  - broker->ingest:hydrogen: grpc × 48
- Fallback deterministic: yes

## Audit Guarantees
- Thermodynamic decisions are streamed to `/var/log/geosync/thermo_audit.jsonl`
  for 7-year retention, ensuring every deviation from invariants is reviewable.
- Circuit breaker blocks topology evolution until an authorised manual override clears
  the halt state.
