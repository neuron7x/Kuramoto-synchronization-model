# Offline Simulation Protocol (forest mode / no stable internet)

One-command benchmark:

```bash
python tools/reset_wave_offline_benchmark.py
```

Artifact output:

- `reports/reset_wave_offline_benchmark_summary.json`

Core metrics:
- `sync_monotonic_rate`
- `async_monotonic_rate`
- `async_lock_rate`

Use this as your local reality anchor while offline:
1. Change model/config.
2. Re-run benchmark.
3. Compare metrics vs previous commit.
4. Accept change only if metrics improve or stay within tolerance with explicit rationale.
