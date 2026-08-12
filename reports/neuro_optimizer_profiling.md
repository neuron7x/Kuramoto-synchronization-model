# NeuroOptimizer profiling notes

## Stepping/loop overview

The per-step loop is driven by `NeuroOptimizer.optimize` in
`src/geosync/core/neuro/neuro_optimizer.py`. Each step performs:

1. `_calculate_balance_metrics` (updates 5 neuromodulator ratios/coherence).
2. `_calculate_objective` (combines performance + balance + stability).
3. `_estimate_gradients` (finite-difference placeholder).
4. `_apply_updates` (momentum update + clipping).
5. `_log_metrics` and iteration bookkeeping.

These are the hot functions to profile.

## How to run the profilers

### cProfile (minimal loop)

```bash
python benchmarks/profile_neuro_optimizer.py
```

Outputs:
- `reports/neuro_optimizer_cprofile.prof`
- `reports/neuro_optimizer_cprofile.txt`

### line_profiler (hot functions)

```bash
python benchmarks/line_profile_neuro_optimizer.py
```

Output:
- `reports/neuro_optimizer_line_profile.txt`

### memory_profiler (allocation peaks)

```bash
python benchmarks/memory_profile_neuro_optimizer.py
```

Output:
- `reports/neuro_optimizer_memory_profile.txt`

## Flame graph generation

Use `py-spy` to capture a flame graph (SVG):

```bash
py-spy record -o reports/neuro_optimizer_flamegraph.svg \
  -- python benchmarks/profile_neuro_optimizer.py
```

## Quick report (current expectations)

- **Hot path**: `_calculate_balance_metrics`, `_calculate_objective`,
  `_apply_updates`, and `_estimate_gradients` dominate per-step time.
- **Allocations**: small array materialization for balance metrics and
  stability statistics; reusing buffers and consistent `float32` helps.
- **Next actions**: consider batching steps or providing vectorized inputs
  for state updates to minimize Python overhead.
