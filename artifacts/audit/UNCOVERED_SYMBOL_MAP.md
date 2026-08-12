# UNCOVERED_SYMBOL_MAP — engine.py (CRITICAL kernel, focus of this PR)

Baseline `core/kuramoto/engine.py` = 91.19% branch. Each missing line classified
by reachability through the **public contract** (`KuramotoConfig` →
`KuramotoEngine` → `KuramotoResult`).

| Line | Symbol | Path | Failure mode if unguarded | Reachable via public API? | Action |
|---|---|---|---|---|---|
| 83 | `KuramotoResult._validate_shapes` | non-finite `order_parameter` guard | `NaN` R leaks past `[0,1]` range check (NaN cmp = False) → INV-K1 violated silently | **Yes** (construct result) | **TEST ADDED** |
| 85 | `KuramotoResult._validate_shapes` | non-finite `time` guard | corrupt time axis stored | **Yes** | **TEST ADDED** |
| 271 | `_dtheta_dt` | non-finite RHS guard | `inf` derivative poisons trajectory | **Yes** (overflow) | **TEST ADDED** |
| 166 | `KuramotoEngine.run` | non-finite phase after RK4 step | — | **No** — `_dtheta_dt`'s own guard (271) fires first; defence-in-depth | **DEFERRED** |
| 237 | `_validate_runtime_inputs` | omega/theta0 shape mismatch | — | **No** — `KuramotoConfig._validate_arrays` (config.py:89-107) rejects upstream | **DEFERRED** |
| 241 | `_validate_runtime_inputs` | adjacency shape mismatch | — | **No** — config.py:109-117 rejects upstream | **DEFERRED** |
| 248 | `_validate_runtime_inputs` | non-finite runtime inputs | — | **No** — config.py finiteness check upstream | **DEFERRED** |

## Invariant-adequacy gap (NOT a line-coverage gap)

| Symbol | Lines | Executed by existing tests? | Decision untested | Action |
|---|---|---|---|---|
| `_rk4_step` | 275-288 | Yes (every sim) | **4th-order convergence** — Euler regression undetected | **TEST ADDED** (Richardson) |
| `_dtheta_dt` | 251-272 | Yes | **rotation equivariance** of coupling term (ω=0) | **TEST ADDED** (metamorphic) |

Deferred items 166/237/241/248 are **defence-in-depth guards that are
unreachable through the validated public contract**. Exercising them would
require bypassing frozen-config validation (object.__setattr__ / monkeypatch),
which the audit charter forbids ("do not test private implementation when public
contract exists", "do not mock kernels"). They are intentionally left
uncovered with this recorded rationale.
