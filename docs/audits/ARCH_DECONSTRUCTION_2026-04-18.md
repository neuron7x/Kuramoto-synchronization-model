# GeoSync Architectural Deconstruction (DESTRUCT_AND_VERIFY)
Date: 2026-04-18 (UTC)
Scope: Python orchestration, Rust acceleration (`rust/geosync-accel`), Go distribution workspace.
Method: static code-path analysis + asymptotic cost modeling.

## 0. Formal Metrics

- Let `N` = input vector length.
- Let `W` = sliding window size.
- Let `S` = step.
- Let `K` = convolution kernel size.
- Let `Q` = quantile request count.
- Let `R = floor((N - W)/S) + 1` (number of windows, if `N >= W`).
- `ΔM` = incremental bytes allocated at a layer boundary.
- `ΔC` = compute saved vs pure Python (not vs NumPy).

## 1. Memory-Phase Invariance: Rust/Python FFI

### 1.1 `sliding_windows`

Data path:
1. Python wrapper canonicalizes input by `np.ascontiguousarray(..., dtype=float64)`.
2. Rust obtains read-only slice via `PyReadonlyArray1::as_slice()`.
3. Rust allocates output `Vec<f64>` of size `R*W` and copies each window.
4. Rust wraps the owned vector into `ndarray::Array2` and then `PyArray2`.

Implications:
- If incoming array is already C-contiguous `float64`: no O(N) input copy at Python boundary.
- If not contiguous or non-`float64`: mandatory O(N) coercion copy before FFI.
- Output requires O(R*W) allocation and copy by design (materialized windows matrix).

Boundary overhead model:
- Best-case `ΔM ≈ 8*R*W` bytes.
- Worst-case `ΔM ≈ 8*N + 8*R*W` bytes.

Safety state:
- No raw pointer escape is visible; borrowed input slices are consumed synchronously, output is owned before return.
- No dangling-pointer vector observed in current implementation.

### 1.2 `convolve`

Data path:
1. Python canonicalizes signal/kernel via `np.ascontiguousarray`.
2. Rust reads slices and computes full convolution into `Vec<f64>` size `N+K-1`.
3. For `same`/`valid`, Rust slices and `to_vec()` again.

Implications:
- `same` and `valid` do a second O(L) allocation (`L = max(N,K)` or `max(N,K)-min(N,K)+1`).
- This is redundant relative to direct single-pass target-length convolution.

Boundary overhead model:
- `full`: `ΔM ≈ 8*(N+K-1)` bytes (+ optional input coercions).
- `same`/`valid`: `ΔM ≈ 8*(N+K-1) + 8*L` bytes (+ optional input coercions).

Conclusion:
- Redundant allocation exists in `convolve_core` for non-`full` modes.
- No dangling-pointer risk detected; risk class is memory-amplification, not memory-unsafety.

## 2. Temporal Desynchronization: Go Workspace Layer

### 2.1 Topology facts

- Root workspace uses only `./examples/go-client`.
- Root `go.mod` is `go 1.22`; example module uses `go 1.24.0`; terraform tests module uses `go 1.25.8`.
- gRPC versions diverge (`1.80.0` in client module vs `1.79.3` indirect in terraform tests workspace sums).

### 2.2 Ricci-signal timestamp propagation analysis

No Rust→Go RPC event carrier was found in repository Go code.
The Go client only:
- probes `/health`,
- establishes a gRPC connection,
- blocks on context cancellation.

There is no event envelope with nanosecond timestamp, no monotonic clock transfer, and no jitter budget enforcement primitive in Go.

Therefore microsecond jitter claim is not implementable in current Go substrate: guarantee function `G(μs<=1)` is undefined because the transport path is absent.

### 2.3 OTel detector race/phantom traces

No Go OpenTelemetry initialization code is present in repository Go source.
OpenTelemetry appears only as indirect dependency in terraform test module graph.

Risk statement:
- Runtime race cannot be triggered from current Go runtime code because detector bootstrap code is absent.
- Build-time temporal aliasing exists: mixed Go toolchains + mixed dependency epochs increase non-deterministic lockfile evolution and reproducibility drift.

## 3. Algorithmic Determinism: Quantiles + Convolution

### 3.1 Quantile algorithm class

Rust quantiles:
- validates probabilities for finite and range,
- checks sortedness O(N),
- sorts full copy if unsorted O(N log N),
- computes linear interpolation O(Q).

Hence total cost:
- sorted input: `T = O(N + Q)`.
- unsorted input: `T = O(N log N + Q)`.

No in-place QuickSelect variant is used. For small `Q` under state saturation (`Q << N`), current approach is asymptotically suboptimal against repeated selection `O(N)`/quantile or multi-select strategies.

### 3.2 NaN/Inf handling

- Probabilities: fail-closed for non-finite/out-of-range.
- Data values: no finiteness rejection. Sorting uses total order; `NaN` participates and can propagate to outputs.
- SIMD/AVX explicit handling is absent; behavior is scalar/high-level control flow.

### 3.3 Convolution determinism

- Inner multiply-accumulate uses `mul_add`, reducing one rounding step vs separate multiply+add.
- Determinism remains platform-dependent for FMA availability and compiler behavior.
- No explicit denormal/NaN policy controls were found.

## 4. Structural Coupling (Interface Leakage)

### 4.1 Coupling map `K`

Define coupling score:
`K = A + B + C`
- `A`: number of cross-layer type coercions per call.
- `B`: number of fallback branches that silently alter execution substrate.
- `C`: number of version/ABI surfaces with independent clocks.

Estimated hotspots:
1. `core/accelerators/numeric.py` ↔ `rust/geosync-accel/src/lib.rs`
   - `A=2` (`ascontiguousarray` + Python list coercion for probabilities in quantiles path)
   - `B=3` (broad exception fallback in sliding/quantiles/convolve)
   - `C=1` (PyO3 ABI surface)
   - `K=6` (high).
2. `go.work` + `go.mod` + `infra/terraform/tests/go.mod`
   - `A=0`, `B=0`, `C=3` (three Go version epochs + divergent grpc/otel dependency clocks)
   - `K=3` (moderate, but build determinism risk).
3. `examples/go-client/cmd/client/main.go`
   - `A=0`, `B=1` (drops `Run` error), `C=0`
   - `K=1` (localized but critical fail-open).

Using `Kc = 4` as criticality threshold, module (1) exceeds `Kc` and is crystallization-prone under failure injection.

## 5. Zero-Day Logic Failures (Fail-Closed Violations)

1. `examples/go-client/cmd/client/main.go`: `Run(...)` error is discarded (`_ = ...`).
   - Failure mode: health/gRPC failures do not surface to process exit code; supervisory systems can misclassify liveness.
   - Class: fail-open control-plane gate.

2. `core/accelerators/numeric.py`: broad `except Exception` around Rust dispatch silently downgrades to NumPy.
   - Failure mode: backend integrity regressions become observability-invisible substrate swaps.
   - Class: fail-open compute substrate gate.

3. `core/accelerators/numeric.py`: quantile entry points `quantiles_rust_backend(...)` and
   `quantiles(...)` are independent, reachable dispatch paths (no dead-branch residue).
   - Integrity note: prior dead-branch claim has been withdrawn as factually incorrect.

## 6. Hardware-Substrate Alignment: `maturin` vs raw C-FFI

Current stack: PyO3 + numpy crate + maturin.

For this workload profile (vectorized batch kernels):
- PyO3 adds call-boundary overhead but enforces lifetime safety and eliminates manual refcount/pointer hazards.
- Dominant costs are data materialization (`R*W` windows, full convolution buffers), not Python call overhead, for medium/large N.

Decision:
- Keep PyO3/maturin unless per-call payload is tiny and invocation frequency is ultra-high (`N < 64`, `calls/sec >> 1e6`) where C-ABI micro-optimizations may dominate.
- If HFT microsecond envelope is hard requirement, primary gain should come from zero-copy window views / streaming kernels, not from replacing maturin alone.

## 7. Hard Remediation Sequence (ordered)

1. Replace `convolve_core` `same`/`valid` slice-copy path with direct target-mode accumulation to remove secondary O(L) allocation.
2. Introduce strict error policy flag in Python accelerator wrapper:
   - `strict_backend=True` => raise on Rust failure (no silent fallback).
3. Normalize Go toolchain epoch across all modules (single Go minor).
4. Add explicit timestamp carrier contract for Rust→Go event path (monotonic + wall clock fields, ns precision).
5. In Go entrypoint, propagate `Run` error to non-zero exit.
6. Replace full-sort quantiles with selection strategy when `Q` is small and `N` is large.

## 8. Verification Status

- Memory safety: no immediate dangling-pointer vectors observed in Rust/PyO3 boundary.
- Latency contract: not verifiable because Rust→Go telemetry pipeline is not implemented in Go codebase.
- Determinism: partial; probability validation is fail-closed, data-value finiteness policy is permissive.
