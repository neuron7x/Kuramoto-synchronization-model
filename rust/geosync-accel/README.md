# geosync-accel

Rust acceleration crate for GeoSync numeric primitives.

This crate exposes sliding window extraction, quantile computation, and 1D convolution
helpers via [PyO3](https://pyo3.rs/) and is packaged with
[`maturin`](https://github.com/PyO3/maturin).

## Building for Python

The crate ships as the optional ``geosync_accel`` Python extension. To build it
locally (for example when working on the GeoSync monorepo) run:

```bash
cd rust/geosync-accel
maturin develop --release
```

Once installed the Python package automatically dispatches to the Rust implementation
whenever it is importable. If the extension is missing, the high level APIs fall back to
NumPy or pure-Python implementations so the platform remains fully functional.


## Validation layers

The Rust accelerator contract is specified in
[`validation_contract.json`](./validation_contract.json). It has four bounded
validation layers:

1. Unit tests cover fixed edge cases for sliding windows, quantiles, and
   convolution modes.
2. Deterministic property tests generate 256 finite signal/kernel pairs from a
   fixed seed and compare every `full`, `same`, and `valid` convolution result
   against an independent reference implementation. This keeps the property
   test reproducible under `cargo test --locked`.
3. Criterion benchmarks run locally and in `rust-accel-gate` as a smoke-level
   CPU regression sentinel for convolution and numeric kernels.
4. A deterministic byte-derived fuzz-smoke test runs under `cargo test`; the
   `cargo-fuzz` target under `fuzz/` remains available for deeper local or
   scheduled fuzzing without adding fuzz-only dependencies to the release gate.

```bash
python scripts/ci/run_rust_accel_contract.py --dry-run --format json
python scripts/ci/run_rust_accel_contract.py --only contract_rest_state --format json
cargo test --locked --manifest-path rust/geosync-accel/Cargo.toml --all-features
cargo bench --locked --manifest-path rust/geosync-accel/Cargo.toml \
  --bench numeric -- --sample-size 10 --warm-up-time 1 --measurement-time 2
# optional deep fuzzing, requires cargo-fuzz:
cd rust/geosync-accel && cargo fuzz run numeric_primitives
```

The contract runner validates the manifest before execution, can emit a JSON
dry-run plan for CI evidence, and exits nonzero if any selected acceptance
criterion fails. Use `--only <criterion_id>` for a bounded repair loop.

## Microbenchmarks

The crate ships with [Criterion](https://bheisler.github.io/criterion.rs/book/index.html)
benchmarks that exercise the sliding window, quantile, and convolution kernels without
going through the Python FFI boundary. To capture a baseline and compare future runs
against it:

```bash
cd rust/geosync-accel
cargo bench -- --save-baseline main
# ... make changes ...
cargo bench -- --baseline main
```

Criterion will highlight statistically significant regressions when the observed slowdown
exceeds the configured noise threshold (1%) or significance level (5%). HTML reports are
written to ``target/criterion`` for deeper inspection.

## Python integration checks

When you need to validate the PyO3 bindings directly from Rust, enable the optional
`python-tests` feature:

```bash
PYO3_PYTHON=python3 cargo test --manifest-path rust/geosync-accel/Cargo.toml --features python-tests
```

Running the tests requires Python development headers to be available for the selected
interpreter. As an alternative you can build the editable wheel and run smoke checks from
Python:

```bash
python -m venv .venv
.venv/bin/python -m pip install maturin numpy
.venv/bin/python -m maturin develop --manifest-path rust/geosync-accel/Cargo.toml
.venv/bin/python - <<'PY'
import numpy as np
import geosync_accel as accel

print(accel.sliding_windows(np.arange(6., dtype=float), window=3, step=2))
print(accel.quantiles(np.array([1.0, 3.0, 2.0, 4.0]), [0.25, 0.5, 0.75]))
print(accel.convolve(np.array([1.0, 2.0, 3.0]), np.array([0.5, 0.5]), 'same'))
PY
```
