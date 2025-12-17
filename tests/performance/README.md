# Performance Test Baselines

This directory contains performance benchmarks and their baseline measurements.

## Baseline History

### kuramoto.compute_phase[128k]

- **Current baseline**: 0.009304s (updated 2025-10-13)
  - **Reason**: Stable CI regressions observed across multiple runs
  - **Note**: Algorithm remains functionally stable; performance variation is due to CI environment differences
  - **Previous baseline**: 0.0079s

### kuramoto.order[4096x12]

- **Current baseline**: 0.00235s

### hierarchical.features[3x2048]

- **Current baseline**: 0.0090s
- **Reference**: Pinned to the 2025 benchmark etalon (see `tests/performance/test_conftest_unit.py`)

## Updating Baselines

When updating baselines in `benchmark_baselines.json`, please:

1. Document the change in this README with:
   - New baseline value
   - Date of update
   - Reason for change
   - Whether the change is due to algorithm changes or environmental factors
   
2. Ensure the change is intentional and validated across multiple runs

3. Keep the commit message descriptive

## Running Benchmarks

```bash
# Run performance tests
pytest tests/performance/ -v --benchmark-only

# Run specific benchmark
pytest tests/performance/test_indicator_benchmarks.py::test_compute_phase_hot_path -v
```
