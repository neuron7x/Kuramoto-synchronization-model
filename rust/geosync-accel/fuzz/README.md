# geosync-accel fuzzing

This directory is intentionally separate from the main crate so normal
`cargo test --locked --manifest-path rust/geosync-accel/Cargo.toml` runs do not
pull fuzzing-only dependencies into the release gate.

Run locally when changing low-level numeric or PyO3 boundary logic:

```bash
cargo install cargo-fuzz
cd rust/geosync-accel
cargo fuzz run numeric_primitives
```

The target feeds bounded finite vectors into sliding-window, quantile, and
convolution kernels to catch panics, invalid indexing, and sanitizer findings.
