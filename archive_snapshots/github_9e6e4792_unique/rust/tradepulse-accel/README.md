# tradepulse-accel

Rust acceleration crate for TradePulse numeric primitives.

This crate exposes sliding window extraction, quantile computation, and 1D convolution
helpers via [PyO3](https://pyo3.rs/) and is packaged with
[`maturin`](https://github.com/PyO3/maturin).

## Building for Python

The crate ships as the optional ``tradepulse_accel`` Python extension. To build it
locally (for example when working on the TradePulse monorepo) run:

```bash
cd rust/tradepulse-accel
maturin develop --release
```

Once installed the Python package automatically dispatches to the Rust implementation
whenever it is importable. If the extension is missing, the high level APIs fall back to
NumPy or pure-Python implementations so the platform remains fully functional.

## Microbenchmarks

The crate ships with [Criterion](https://bheisler.github.io/criterion.rs/book/index.html)
benchmarks that exercise the sliding window, quantile, and convolution kernels without
going through the Python FFI boundary. To capture a baseline and compare future runs
against it:

```bash
cd rust/tradepulse-accel
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
PYO3_PYTHON=python3 cargo test --manifest-path rust/tradepulse-accel/Cargo.toml --features python-tests
```

Running the tests requires Python development headers to be available for the selected
interpreter. As an alternative you can build the editable wheel and run smoke checks from
Python:

```bash
python -m venv .venv
.venv/bin/python -m pip install maturin numpy
.venv/bin/python -m maturin develop --manifest-path rust/tradepulse-accel/Cargo.toml
.venv/bin/python - <<'PY'
import numpy as np
import tradepulse_accel as accel

print(accel.sliding_windows(np.arange(6., dtype=float), window=3, step=2))
print(accel.quantiles(np.array([1.0, 3.0, 2.0, 4.0]), [0.25, 0.5, 0.75]))
print(accel.convolve(np.array([1.0, 2.0, 3.0]), np.array([0.5, 0.5]), 'same'))
PY
```
