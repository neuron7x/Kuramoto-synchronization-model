# MATH AUDIT REPORT (TradePulse — math-hardening baseline)

## Scope & Inventory

- **analytics/math_trading/**
  - `kelly_criterion.py`: single-asset Kelly, multi-asset Kelly (matrix solve + constrained SLSQP), edge/variance helper, historical estimator.
  - `optimal_execution.py`: Almgren–Chriss execution schedule (hyperbolic/linear trajectory), VWAP fallback.
  - `portfolio_rebalancing.py`: quadratic program with L1/L2 costs, tolerance bands, turnover cap, minimum trade size, optional variance-aware scaling.
- **analytics/regime/**
  - `core/ews.py`: ensemble early warning scorer combining FK, Ricci, topology, causal guard; kill-switch policy gates.
  - `core/ricci_flow.py`: curvature-driven gradient flow + simplex projection for weights.
  - (not yet deep-reviewed: `fk_detector`, `topo_sentinel`, `causal_guard`, `tradepulse_v21`, adapters/consensus layers).
- **core/indicators/**
  - `trading.py`: streaming helpers (rolling sums, smoothing, GPU/numba backends), Hurst/phase wrappers, weighting & NaN handling.
  - Additional indicators (entropy, Ricci variants, multiscale Kuramoto, fractal features) require later passes.

## Specifications (current behavior)

### Kelly Criterion (single-asset)
- **Definition**: Full Kelly `f* = (b*p - (1-p))/b`; fractional scaling and clamp to `[0, max_fraction]`.
- **Domain**: `0<p<1`, `b>0`, `max_fraction>0`, `0<f_k<=1`.
- **Outputs**: `optimal_fraction`, `full_kelly`, `edge = p*b - (1-p)`, `growth_rate = p ln(1+f b) + (1-p) ln(1-f)` if `0<f<1`, else `0`; max drawdown ≈ `2f/(1+f)`.
- **NaN/Inf policy**: no explicit sanitization; invalid params raise; log undefined if `f>=1` guarded by branch.
- **Tolerance/precision**: none documented; float64 ops.

### Multi-Asset Kelly
- **Definition**: Unconstrained `Σ^{-1}(μ - r_f)`, then fractional scaling; constrained SLSQP on bounded positions with soft leverage penalty; utility ≈ mean-variance form `E[r_p] - 0.5·Var[r_p]` (risk aversion implicitly 1).
- **Domain**: square covariance; shape-consistent `mu`; `0<f_k<=1`; leverage >0, max_position>0.
- **Invariants**: leverage <= max_leverage (soft), |position|<=max_position (hard); covariance invertible or pinv fallback.
- **NaN/Inf policy**: none; sigma inversion may propagate NaN; no PSD check.
- **Stability**: uses `inv`; falls back to `pinv`; no conditioning diagnostics; gradient analytic.

### Historical Kelly Estimator
- **Definition**: sample mean/cov over trailing window; same optimizer.
- **Domain**: 2D returns; `lookback` slice; sigma forced 2D.
- **NaN policy**: none; sample moments will propagate NaN/Inf.

### Almgren–Chriss Optimal Execution
- **Definition**: kappa = sqrt(lambda * σ_sec^2 / eta); trajectory hyperbolic (sinh) or linear fallback; slice qty = Δtrajectory; temporary impact = eta*(rate)*dt; permanent cost = γ X^2/2; risk = σ_sec^2 Σ_k x_k^2 dt; objective = shortfall + λ·risk.
- **Domain**: `total_quantity != 0`, `duration>0`, `vol>0`, `eta>=0`, `gamma>=0`, `lambda>=0`; `num_slices>0`.
- **Invariants**: trajectory monotone with sign of `X`; weights sum to `X`; time grid evenly spaced.
- **NaN policy**: none; sigma scaling uses math.sqrt; sinh guard for tiny kappa.
- **Stability**: uses sinh guard; no explicit overflow/underflow controls.

### VWAP Schedule
- **Definition**: allocate `total_quantity * weight_i` where weights = volume_profile / sum(volume_profile); no impact modeled.
- **Domain**: non-empty profile; positive duration; sum(profile)>0.
- **NaN policy**: none; uses Python sums.

### Portfolio Rebalancer (QP)
- **Definition**: minimize `Σ c_i t_i + λ ||w-w_target||_2^2` with auxiliary `t_i >= |w_i - w_current|`; constraints: weights sum=1, tolerance bands, turnover cap, bounds (long-only optional), min trade size post-solve zeroing.
- **Domain**: weights provided; portfolio_value>0; tolerances >=0; turnover>0.
- **Invariants**: Σ w = 1 (linear constraint); if long-only then w>=0; |w-w*|<=tol; turnover<=max; min trade zeroes tiny trades.
- **NaN policy**: none; np arrays default float.
- **Stability**: uses SLSQP; gradients provided; no Hessian; feasible set not pre-checked for tol vs sum; potential infeasibility.

### Minimum-Variance Trades helper
- **Definition**: scale delta to satisfy variance change <= risk_budget solving quadratic for α in [0,1].
- **Domain**: covariance square; asset order matches.
- **NaN policy**: none; discriminant guard <0 → α=0.

### EWS Ensemble
- **Definition**: score = w_fk·FK + w_ricci·(1-ricci_mean) + w_topo·topo + w_causal·causal + bias; probability = sigmoid(score); kill-switch if online AUC below min or FPR above max.
- **Domain**: inputs are results with scalar attributes; weights real.
- **Invariants**: probability in (0,1); kill-switch boolean.
- **NaN policy**: none; exp overflow possible for large |score|.

### Ricci Flow Rebalancer
- **Definition**: curvature weights = exp(-β(1-corr)); curvature mean; gradient = (curvature - mean) - λ·(2 Σ_cov @ w_prev) where Σ_cov is the covariance matrix and the factor 2 comes from ∇(w^T Σ w); candidate = prev + step·gradient; blended with turnover penalty; projected onto simplex with lower bound.
- **Domain**: covariance square; correlation provided or derived; lower_bound feasible (n*lb<=1).
- **Invariants**: weights on simplex; curvature array size = assets; ricci_mean scalar.
- **NaN policy**: corr computed with `errstate`; clipped [-1,1]; no NaN drop if std=0 leads to NaN but later clipped.
- **Stability**: uses explicit projection; no line search; fixed step.

### Indicators (trading.py core helpers)
- **Definition**: rolling sums (CPU/CuPy/CUDA); smoothing; NaN filling via interpolation; Hurst kernel with numba; weighting series with modes.
- **Domain**: 1D arrays; window>0; volumes non-negative.
- **NaN policy**: `np.nan_to_num` for weights; `_fill_missing` interpolates finite values.
- **Stability**: guards for tiny windows; GPU fallbacks; no epsilon for division in hurst kernels.

## Risk & Failure Modes

- **Kelly (multi)**: using `inv` on poorly conditioned covariance can explode; no PSD check; leverage soft-penalty may be violated by optimizer tolerance; no guard on negative variance / NaN returns. `growth_rate` uses approximation; no log-sum-exp stability.
- **Single Kelly**: growth rate undefined for `f>=1` handled by branch but no check for `full_kelly<0` (returns 0 after clamp, losing signal); no NaN sanitization.
- **Almgren–Chriss**: assumes linear impact; no guard for extreme `volatility` (overflow in kappa); risk uses sigma_sec^2 without cap; no NaN rejection of profile.
- **Rebalancer**: feasible set may be empty (tolerance + long-only + sum=1) → SLSQP may fail silently with `success=False`; no check that `w_current` within bounds; min trade post-constraint can break Σw=1 slightly (though constraint enforces before zeroing).
- **Minimum-variance**: discriminant negative → α=0 returns no trades even if small feasible; no PSD validation.
- **EWS**: uncalibrated weight scale; sigmoid overflow risk; probability not bounded for extreme scores in float (exp over/underflow).
- **Ricci Flow**: correlation from cov with zero std → NaN then clipped; simplex guard only against lb infeasible; gradient step fixed—possible oscillation; no seed/determinism concerns.
- **Indicators**: `_fill_missing` interpolates infinite values to zeros; rolling sum GPU path may throw; no tolerance for extremely large values leading to overflow.

## Validation Matrix (current vs needed)

| Component | Invariants | Tests | Tolerance | Edge cases | Status |
| --- | --- | --- | --- | --- | --- |
| Single-asset Kelly | 0<p<1, b>0, 0<=f<=max_fraction; growth_rate finite | **Missing** (unit calc) | exact calc / float tol 1e-9 | p→0/1, b→0+, fractional_kelly<1, clamp at max_fraction | Gaps |
| Multi-asset Kelly | Σ symmetric/PSD; |f_i|<=max_position; leverage<=max_leverage | **Missing** (reference solve, leverage property) | rtol 1e-6 on allocations | singular Σ, highly correlated assets, negative returns, NaN | Gaps |
| Historical Kelly | sample mean/cov correct; lookback slicing | **Missing** | rtol 1e-6 | 1-period data, constant series, NaN row | Gaps |
| Almgren–Chriss | monotone trajectory, Σ qty=Q, costs non-negative | **Missing** | atol 1e-9 sums | zero risk aversion path linear, tiny eta, large vol | Gaps |
| VWAP | weights sum=1, cumulative matches Q | **Missing** | atol 1e-12 | zero volume bucket, negative inputs rejected | Gaps |
| Portfolio Rebalancer | Σ w=1, tolerance bands respected, turnover cap | **Missing** | atol 1e-8 | infeasible tolerance, long-only vs shorts, min_trade zeroing | Gaps |
| Min-variance trades | variance change <= budget | **Missing** | rtol 1e-8 | PSD vs indefinite Σ, discriminant<0 | Gaps |
| EWS Ensemble | prob∈(0,1), weights applied correctly | **Missing** | atol 1e-12 prob | extreme scores, missing causal input | Gaps |
| Ricci Flow | weights on simplex, ricci_mean finite | **Missing** | atol 1e-10 sum | zero-std cov, lb infeasible, negative corr | Gaps |
| Indicators (rolling/smoothing) | window>0 guard, NaN handling | **Partial** (some coverage elsewhere) | atol 1e-12 sums | empty array, huge window, GPU fallback failure | Gaps |

## PR Series Plan (minimum 3 PRs)

1. **PR1 — Specs & Baseline Tests**
   - Add detailed doc/spec blocks for Kelly (single/multi), Almgren–Chriss, VWAP, Rebalancer, Ricci Flow, EWS.
   - Add deterministic unit tests + small-sample golden cases; seed RNG with `np.random.default_rng`.
   - Add property tests for invariants (probability bounds, simplex sums, leverage limits) using Hypothesis if available.
   - Acceptance: tests passing locally; documentation reflecting domains/invariants; no functional changes.
2. **PR2 — Numerical Stability & Correctness**
   - Replace `inv` with `solve`/`pinv` with conditioning guard; PSD checks with eigenvalue floor; leverage hard constraint or penalty tightening.
   - Add NaN/Inf sanitization and explicit error paths; stabilize sigmoid with clipping; ensure monotone trajectory and sum(Q) after min_trade.
   - Acceptance: new tests demonstrating stability on ill-conditioned covariance and extreme scores; risk of regression mitigated by golden outputs.
3. **PR3 — Security, Reproducibility, Dependency Hardening**
   - Enforce deterministic seeds in stochastic paths; add input validation for volume profiles, covariance; add bounds to exp/sinh operations.
   - Review and tighten dependency pins if touched; add docs on NaN-policy and reproducibility knobs.
   - Acceptance: security checks pass; reproducibility toggles documented; property tests for path sanitization.

## Outstanding Evidence

- Pytest unavailable in current environment (`pytest: command not found`); no tests executed yet. Need environment with project deps to validate PRs.
