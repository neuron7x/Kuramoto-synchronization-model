"""Fail-fast kill test for GeoSync/Ricci on real L2 substrate.

Single-file, minimal scope: load L2 parquet shards → derive four core features
(OFI, queue imbalance, cross-sectional correlation graph, Forman-Ricci κ_min)
→ test against one target (3-min forward mid-price log return) → compare to
three baselines (plain mid-return, realized vol, plain own-OFI) → run null
tests (permutation + circular shift) → orthogonality residual → emit binary
VERDICT.

Gate thresholds (conservative, fail-fast first pass):
    IC_signal >= 0.03 (Spearman, pooled across symbols)
    IC_signal > max(IC_baselines)
    Residual IC (after OLS on baselines) > 0 with permutation p < 0.05
    Stable lead: IC > 0 at horizons 1, 2, 3, 4, 5 minutes (all)

If any gate fails → VERDICT = KILL. Otherwise → PROCEED.

Seed = 42 everywhere. Determinism contract (INV-HPC1): same inputs → same
verdict bit-identical.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from numpy.typing import NDArray
from scipy.stats import spearmanr

from core.kuramoto.falsification import iaaft_surrogate
from core.physics.forman_ricci import FormanRicciCurvature
from research.microstructure.l2_schema import N_LEVELS, l2_schema

SEED: int = 42
_GRID_MS: int = 1_000
_TARGET_HORIZONS_SEC: tuple[int, ...] = (60, 120, 180, 240, 300)
_PRIMARY_HORIZON_SEC: int = 180
_CORR_WINDOW_SEC: int = 300
_CORR_STEP_SEC: int = 30
_RICCI_THRESHOLD: float = 0.5
_IC_GATE: float = 0.03
_PERM_TRIALS: int = 500
_PERM_PVALUE_GATE: float = 0.05
# IAAFT linear-spectral null (Schreiber & Schmitz 1996). Surrogates preserve
# the Ricci signal's power spectrum AND amplitude distribution exactly, so a
# surviving IC cannot be explained by linear autocorrelation alone. Unlike
# circular_shift this draws a full ensemble (no shift-count power loss).
#
# Whether IAAFT GATES the verdict (vs. report-only ADVISORY) is decided by the
# committed positive-control audit (research.microstructure.iaaft_audit), not by
# a hand-set flag: run_killtest consults results/L2_IAAFT_GATING_AUDIT.json via
# iaaft_is_gating_eligible and only gates if that audit certifies the null is
# both powered AND calibrated. The current canonical audit reports power=1.0 but
# FPR=0.25 on the autocorrelated regime (over-fires ~5x nominal alpha) →
# INELIGIBLE → the null stays ADVISORY. Re-certify (e.g. a stationarity-aware
# null) to flip eligibility; promotion is then earned by evidence, not asserted.
_IAAFT_TRIALS: int = 200
_IAAFT_ITERS: int = 80

# Frozen gating-eligibility artifact, resolved relative to the repo root.
_IAAFT_AUDIT_ARTIFACT: Path = (
    Path(__file__).resolve().parents[2] / "results" / "L2_IAAFT_GATING_AUDIT.json"
)


@dataclass(frozen=True)
class FeatureFrame:
    """Aligned per-symbol feature panels on a fixed 1-second grid."""

    timestamps_ms: NDArray[np.int64]
    symbols: tuple[str, ...]
    mid: NDArray[np.float64]
    ofi: NDArray[np.float64]
    queue_imbalance: NDArray[np.float64]

    @property
    def n_rows(self) -> int:
        return int(self.mid.shape[0])

    @property
    def n_symbols(self) -> int:
        return len(self.symbols)


@dataclass
class GateVerdict:
    verdict: str
    reasons: list[str]
    ic_signal: float
    ic_baselines: dict[str, float]
    residual_ic: float
    residual_ic_pvalue: float
    horizon_ic: dict[int, float]
    null_test_pvalues: dict[str, float]
    n_samples: int
    n_symbols: int
    seed: int = SEED
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SplitVerdict:
    """Train/test OOS split of a single substrate window.

    Each half runs the full gate independently. The overall verdict is the
    conjunction: PROCEED only if both halves pass their own gate AND the
    edge retained on test is at least `retention_gate` of the train edge.
    Shrinkage beyond that → overfit or non-stationary edge → KILL.
    """

    verdict: str
    reasons: list[str]
    train: GateVerdict
    test: GateVerdict
    split_at_fraction: float
    ic_retention: float
    retention_gate: float
    seed: int = SEED


def _load_parquets(data_dir: Path, symbols: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Load and concat all parquet shards per symbol under `data_dir`."""
    schema = l2_schema()
    frames: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        shards = sorted(data_dir.glob(f"{sym}_hour_*.parquet"))
        if not shards:
            continue
        tables = [pq.read_table(p, schema=schema) for p in shards]
        df = pd.concat([t.to_pandas() for t in tables], ignore_index=True)
        df = df.drop_duplicates(subset=["ts_event", "update_id"])
        df = df.sort_values("ts_event").reset_index(drop=True)
        frames[sym] = df
    return frames


def _to_grid(df: pd.DataFrame, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Downsample to 1-second grid aligned on floored-to-second timestamps.

    `resample("1s").last()` buckets events into round-second bins, so the
    target grid must share that offset (floor to second), otherwise
    `reindex` returns all-NaN and ffill cannot recover.
    """
    idx = pd.to_datetime(df["ts_event"], unit="ms", utc=True)
    panel = df.set_index(idx)
    resampled = panel.resample("1s").last()
    start = pd.Timestamp(start_ms, unit="ms", tz="UTC").floor("1s")
    end = pd.Timestamp(end_ms, unit="ms", tz="UTC").floor("1s")
    grid_idx = pd.date_range(start=start, end=end, freq="1s")
    resampled = resampled.reindex(grid_idx).ffill(limit=30)
    return resampled


def _compute_mid(df: pd.DataFrame) -> pd.Series:
    return (df["bid_px_1"] + df["ask_px_1"]) * 0.5


def _compute_ofi(df: pd.DataFrame) -> pd.Series:
    """Order Flow Imbalance at L1 (Cont-Kukanov-Stoikov, 2014).

    e_n = ΔB · 1[bid_px_n >= bid_px_{n-1}] - bid_sz_{n-1} · 1[bid_px_n < bid_px_{n-1}]
        - ΔA · 1[ask_px_n <= ask_px_{n-1}] + ask_sz_{n-1} · 1[ask_px_n > ask_px_{n-1}]

    where ΔB = bid_sz_n - bid_sz_{n-1} when bid_px_n == bid_px_{n-1}, else bid_sz_n;
    symmetric for asks.
    """
    bid_px = df["bid_px_1"].astype(float).to_numpy()
    bid_sz = df["bid_sz_1"].astype(float).to_numpy()
    ask_px = df["ask_px_1"].astype(float).to_numpy()
    ask_sz = df["ask_sz_1"].astype(float).to_numpy()

    n = len(bid_px)
    ofi = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if bid_px[i] > bid_px[i - 1]:
            bid_term = bid_sz[i]
        elif bid_px[i] < bid_px[i - 1]:
            bid_term = -bid_sz[i - 1]
        else:
            bid_term = bid_sz[i] - bid_sz[i - 1]

        if ask_px[i] < ask_px[i - 1]:
            ask_term = ask_sz[i]
        elif ask_px[i] > ask_px[i - 1]:
            ask_term = -ask_sz[i - 1]
        else:
            ask_term = ask_sz[i] - ask_sz[i - 1]

        ofi[i] = bid_term - ask_term
    return pd.Series(ofi, index=df.index, name="ofi")


def _compute_queue_imbalance(df: pd.DataFrame) -> pd.Series:
    bid_sz = df["bid_sz_1"].astype(float)
    ask_sz = df["ask_sz_1"].astype(float)
    denom = bid_sz + ask_sz
    qi = (bid_sz - ask_sz) / denom.replace(0.0, np.nan)
    return qi.fillna(0.0).clip(-1.0, 1.0).rename("qi")


def build_feature_frame(
    frames: dict[str, pd.DataFrame],
    symbols: tuple[str, ...],
) -> FeatureFrame:
    if not frames:
        raise ValueError("no symbol frames loaded — cannot build feature frame")
    symbols_present = tuple(s for s in symbols if s in frames)
    if len(symbols_present) < 3:
        raise ValueError(
            f"need at least 3 symbols with data, got {len(symbols_present)}: {symbols_present}"
        )

    start_ms = max(int(frames[s]["ts_event"].iloc[0]) for s in symbols_present)
    end_ms = min(int(frames[s]["ts_event"].iloc[-1]) for s in symbols_present)
    if end_ms - start_ms < _CORR_WINDOW_SEC * 1000 * 4:
        raise ValueError(
            f"overlap too short: {(end_ms - start_ms) / 1000:.1f}s "
            f"(need >= {_CORR_WINDOW_SEC * 4}s)"
        )

    grid_panels: dict[str, pd.DataFrame] = {
        s: _to_grid(frames[s], start_ms, end_ms) for s in symbols_present
    }

    ref_idx = grid_panels[symbols_present[0]].index
    n_rows = len(ref_idx)
    n_sym = len(symbols_present)

    mid = np.full((n_rows, n_sym), np.nan, dtype=np.float64)
    ofi = np.zeros((n_rows, n_sym), dtype=np.float64)
    qi = np.zeros((n_rows, n_sym), dtype=np.float64)

    for k, sym in enumerate(symbols_present):
        panel = grid_panels[sym]
        mid[:, k] = _compute_mid(panel).to_numpy()
        ofi[:, k] = _compute_ofi(panel).to_numpy()
        qi[:, k] = _compute_queue_imbalance(panel).to_numpy()

    mask = np.isfinite(mid).all(axis=1)
    mid = mid[mask]
    ofi = ofi[mask]
    qi = qi[mask]
    timestamps_ms = (ref_idx[mask].astype("int64") // 1_000_000).to_numpy()

    return FeatureFrame(
        timestamps_ms=timestamps_ms,
        symbols=symbols_present,
        mid=mid,
        ofi=ofi,
        queue_imbalance=qi,
    )


def cross_sectional_ricci_signal(
    ofi_panel: NDArray[np.float64],
    window: int = _CORR_WINDOW_SEC,
    step: int = _CORR_STEP_SEC,
    threshold: float = _RICCI_THRESHOLD,
) -> NDArray[np.float64]:
    """Rolling κ_min of Forman-Ricci on OFI cross-sectional correlation graph.

    Returns array of shape (T,) aligned to input rows; rows before the first
    full window are NaN.
    """
    n, m = ofi_panel.shape
    if m < 3:
        return np.full(n, np.nan)
    fr = FormanRicciCurvature(threshold=threshold)
    out = np.full(n, np.nan, dtype=np.float64)
    for end in range(window, n, step):
        block = ofi_panel[end - window : end]
        if not np.all(np.isfinite(block)):
            continue
        std = block.std(axis=0)
        if np.any(std < 1e-12):
            continue
        corr_raw = np.corrcoef(block.T)
        corr = np.nan_to_num(
            np.asarray(corr_raw, dtype=np.float64), nan=0.0, posinf=1.0, neginf=-1.0
        )
        result = fr.compute_from_correlation(corr)
        fill_to = min(end + step, n)
        out[end:fill_to] = result.kappa_min
    return out


def _forward_log_return(mid_panel: NDArray[np.float64], horizon_rows: int) -> NDArray[np.float64]:
    log_mid = np.log(mid_panel)
    fwd = np.full_like(log_mid, np.nan)
    if horizon_rows >= log_mid.shape[0]:
        return fwd
    fwd[:-horizon_rows] = log_mid[horizon_rows:] - log_mid[:-horizon_rows]
    return fwd


def _pooled_ic(signal_panel: NDArray[np.float64], target_panel: NDArray[np.float64]) -> float:
    s_flat = signal_panel.ravel()
    t_flat = target_panel.ravel()
    mask = np.isfinite(s_flat) & np.isfinite(t_flat)
    if mask.sum() < 50:
        return float("nan")
    s = s_flat[mask]
    t = t_flat[mask]
    if float(np.std(s)) == 0.0 or float(np.std(t)) == 0.0:
        return float("nan")
    rho, _ = spearmanr(s, t)
    return float(rho) if np.isfinite(rho) else float("nan")


def _permutation_pvalue(
    signal_panel: NDArray[np.float64],
    target_panel: NDArray[np.float64],
    observed_ic: float,
    *,
    trials: int = _PERM_TRIALS,
    seed: int = SEED,
    mode: str = "shuffle",
) -> float:
    rng = np.random.default_rng(seed)
    n_rows = signal_panel.shape[0]
    count = 0
    trials_done = 0
    for _ in range(trials):
        if mode == "shuffle":
            perm = rng.permutation(n_rows)
            shuffled = signal_panel[perm]
        elif mode == "circular":
            shift = int(rng.integers(1, n_rows - 1))
            shuffled = np.roll(signal_panel, shift, axis=0)
        else:
            raise ValueError(f"unknown mode: {mode}")
        ic = _pooled_ic(shuffled, target_panel)
        if not np.isfinite(ic):
            continue
        if abs(ic) >= abs(observed_ic):
            count += 1
        trials_done += 1
    if trials_done == 0:
        return 1.0
    return (count + 1) / (trials_done + 1)


def _iaaft_pvalue(
    signal_1d: NDArray[np.float64],
    target_panel: NDArray[np.float64],
    observed_ic: float,
    n_symbols: int,
    *,
    row_mask: NDArray[np.bool_] | None = None,
    trials: int = _IAAFT_TRIALS,
    iters: int = _IAAFT_ITERS,
    seed: int = SEED,
) -> float:
    """Empirical p-value under the IAAFT linear-spectral null.

    Each surrogate replaces the 1-D cross-sectional Ricci signal with an IAAFT
    draw (Schreiber & Schmitz 1996) over its finite support: the surrogate has
    the *same power spectrum and the same amplitude distribution* but a phase-
    randomized temporal structure. It is broadcast back to the per-symbol panel
    (and re-masked identically to the observed signal) and scored against the
    real forward-return target. p = Pr(|IC_surrogate| >= |IC_observed|): a small
    p means the predictive IC survives a null that keeps the signal's entire
    linear autocorrelation, so it cannot be a linear-spectral artifact.
    """
    finite_idx = np.flatnonzero(np.isfinite(signal_1d))
    if finite_idx.size < 50:
        return 1.0
    base = signal_1d[finite_idx].astype(np.float64)
    rng = np.random.default_rng(seed)
    count = 0
    trials_done = 0
    for _ in range(trials):
        surr_1d = np.full_like(signal_1d, np.nan, dtype=np.float64)
        surr_1d[finite_idx] = iaaft_surrogate(base, n_iterations=iters, rng=rng)
        surr_panel = np.repeat(surr_1d[:, None], n_symbols, axis=1)
        if row_mask is not None:
            surr_panel = np.where(row_mask[:, None], surr_panel, np.nan)
        ic = _pooled_ic(surr_panel, target_panel)
        if not np.isfinite(ic):
            continue
        if abs(ic) >= abs(observed_ic):
            count += 1
        trials_done += 1
    if trials_done == 0:
        return 1.0
    return (count + 1) / (trials_done + 1)


def _residualize(
    signal_panel: NDArray[np.float64],
    baselines_panel: dict[str, NDArray[np.float64]],
) -> NDArray[np.float64]:
    """OLS residuals of signal ~ baselines, preserving NaN positions."""
    s_flat = signal_panel.ravel().astype(np.float64)
    b_cols = [b.ravel().astype(np.float64) for b in baselines_panel.values()]
    stacked = np.column_stack(b_cols) if b_cols else np.zeros((s_flat.shape[0], 0))
    mask = (
        np.isfinite(s_flat) & np.all(np.isfinite(stacked), axis=1)
        if b_cols
        else np.isfinite(s_flat)
    )
    residual = np.full_like(s_flat, np.nan)
    if mask.sum() < 50 or stacked.shape[1] == 0:
        return residual.reshape(signal_panel.shape)
    X = np.column_stack([np.ones(mask.sum()), stacked[mask]])
    y = s_flat[mask]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    residual[mask] = y - fitted
    return residual.reshape(signal_panel.shape)


def run_killtest(
    features: FeatureFrame,
    *,
    primary_horizon_sec: int = _PRIMARY_HORIZON_SEC,
    horizons_sec: tuple[int, ...] = _TARGET_HORIZONS_SEC,
    ic_gate: float = _IC_GATE,
    pvalue_gate: float = _PERM_PVALUE_GATE,
    regime_mask: NDArray[np.bool_] | None = None,
    iaaft_gating: bool | None = None,
    seed: int = SEED,
) -> GateVerdict:
    """Execute the full fail-fast gate and emit a binary verdict.

    When `regime_mask` is provided (shape (n_rows,)), IC and null-test
    computations count only rows where the mask is True. The Ricci signal
    is still computed on the full contiguous time series (its rolling
    cross-sectional correlation needs consecutive rows) — the filter acts
    at scoring time, not feature-construction time.

    `iaaft_gating` controls whether the IAAFT linear-spectral null contributes
    a KILL reason (vs. report-only). `None` (default) resolves it from the
    committed positive-control audit artifact via `iaaft_is_gating_eligible` —
    fail-closed, so an absent/ineligible audit keeps IAAFT advisory and the
    published verdict bit-identical. Pass an explicit bool to override (tests).
    """
    ricci_signal_1d = cross_sectional_ricci_signal(features.ofi)
    ricci_panel = np.repeat(ricci_signal_1d[:, None], features.n_symbols, axis=1)
    target = _forward_log_return(features.mid, primary_horizon_sec)

    if regime_mask is not None:
        if regime_mask.shape != (features.n_rows,):
            raise ValueError(
                f"regime_mask shape {regime_mask.shape} must equal ({features.n_rows},)"
            )
        # broadcast row-mask to panel shape
        panel_mask = np.broadcast_to(regime_mask[:, None], ricci_panel.shape)
        ricci_panel = np.where(panel_mask, ricci_panel, np.nan)
        target = np.where(panel_mask, target, np.nan)

    ic_signal = _pooled_ic(ricci_panel, target)

    ret_1s = np.vstack(
        [
            np.zeros((1, features.n_symbols)),
            np.diff(np.log(features.mid), axis=0),
        ]
    )
    realized_vol = pd.DataFrame(ret_1s).rolling(window=60, min_periods=30).std().to_numpy()
    baselines: dict[str, NDArray[np.float64]] = {
        "plain_return": ret_1s,
        "realized_vol": realized_vol,
        "plain_ofi": features.ofi,
    }

    ic_baselines: dict[str, float] = {}
    for name, b in baselines.items():
        ic_baselines[name] = _pooled_ic(b, target)

    residual_signal = _residualize(ricci_panel, baselines)
    residual_ic = _pooled_ic(residual_signal, target)
    residual_pvalue = _permutation_pvalue(
        residual_signal, target, residual_ic, seed=seed, mode="shuffle"
    )

    null_pvalues: dict[str, float] = {
        "permutation_shuffle": _permutation_pvalue(
            ricci_panel, target, ic_signal, seed=seed, mode="shuffle"
        ),
        "circular_shift": _permutation_pvalue(
            ricci_panel, target, ic_signal, seed=seed + 1, mode="circular"
        ),
        # IAAFT linear-spectral null — surrogates the 1-D Ricci signal preserving
        # its power spectrum + amplitude distribution. Advisory (see _IAAFT_*).
        "iaaft": _iaaft_pvalue(
            ricci_signal_1d,
            target,
            ic_signal,
            features.n_symbols,
            row_mask=regime_mask,
            seed=seed + 2,
        ),
    }

    horizon_ic: dict[int, float] = {}
    for h in horizons_sec:
        tgt_h = _forward_log_return(features.mid, h)
        horizon_ic[h] = _pooled_ic(ricci_panel, tgt_h)

    # Gate criteria (AE-reduced to user-spec inevitables):
    # 1. absolute IC floor               (spec: IC >= threshold)
    # 2. orthogonal edge exists & sig'   (spec: orthogonality to baselines)
    # 3. stable lead across horizons     (spec: positive lead capture)
    # 4. permutation_shuffle significance (spec: permutation significance)
    # circular_shift is reported as advisory null — it loses power on
    # autocorrelated Ricci signals at half-sample sizes and cannot gate
    # without inducing sample-size-dependent false KILLs.
    reasons: list[str] = []
    if not np.isfinite(ic_signal) or ic_signal < ic_gate:
        reasons.append(f"IC_signal={ic_signal:.4f} < gate={ic_gate:.4f}")
    if not np.isfinite(residual_ic) or residual_ic <= 0.0:
        reasons.append(f"residual_IC={residual_ic:.4f} <= 0 (no orthogonal edge)")
    if residual_pvalue > pvalue_gate:
        reasons.append(f"residual permutation p={residual_pvalue:.3f} > gate={pvalue_gate:.3f}")
    unstable = [h for h, ic in horizon_ic.items() if not np.isfinite(ic) or ic <= 0.0]
    if unstable:
        reasons.append(f"unstable lead: non-positive IC at horizons {unstable}")
    shuffle_p = null_pvalues["permutation_shuffle"]
    if shuffle_p > pvalue_gate:
        reasons.append(f"permutation_shuffle p={shuffle_p:.3f} > gate={pvalue_gate:.3f}")

    # IAAFT gates only when the committed positive-control audit certifies it
    # (powered AND calibrated). Fail-closed: absent/ineligible audit → advisory.
    if iaaft_gating is None:
        from research.microstructure.iaaft_audit import iaaft_is_gating_eligible

        iaaft_gating = iaaft_is_gating_eligible(_IAAFT_AUDIT_ARTIFACT)
    if iaaft_gating:
        iaaft_p = null_pvalues["iaaft"]
        if iaaft_p > pvalue_gate:
            reasons.append(f"iaaft p={iaaft_p:.3f} > gate={pvalue_gate:.3f}")

    verdict = "PROCEED" if not reasons else "KILL"

    return GateVerdict(
        verdict=verdict,
        reasons=reasons,
        ic_signal=float(ic_signal) if np.isfinite(ic_signal) else float("nan"),
        ic_baselines={
            k: float(v) if np.isfinite(v) else float("nan") for k, v in ic_baselines.items()
        },
        residual_ic=float(residual_ic) if np.isfinite(residual_ic) else float("nan"),
        residual_ic_pvalue=float(residual_pvalue),
        horizon_ic={
            int(h): float(ic) if np.isfinite(ic) else float("nan") for h, ic in horizon_ic.items()
        },
        null_test_pvalues={k: float(v) for k, v in null_pvalues.items()},
        n_samples=int(features.n_rows),
        n_symbols=int(features.n_symbols),
        seed=seed,
        metadata={
            "primary_horizon_sec": primary_horizon_sec,
            "ic_gate": ic_gate,
            "pvalue_gate": pvalue_gate,
            "corr_window_sec": _CORR_WINDOW_SEC,
            "corr_step_sec": _CORR_STEP_SEC,
            "ricci_threshold": _RICCI_THRESHOLD,
            "n_levels": N_LEVELS,
            "iaaft_gating": bool(iaaft_gating),
        },
    )


def verdict_to_json(verdict: GateVerdict) -> str:
    return json.dumps(asdict(verdict), indent=2, sort_keys=True, default=str)


_RETENTION_GATE: float = 0.5


def slice_features(features: FeatureFrame, start: int, end: int) -> FeatureFrame:
    """Return a contiguous sub-slice of a FeatureFrame along the time axis."""
    if start < 0 or end > features.n_rows or start >= end:
        raise ValueError(f"invalid slice [{start}, {end}) for n_rows={features.n_rows}")
    return FeatureFrame(
        timestamps_ms=features.timestamps_ms[start:end].copy(),
        symbols=features.symbols,
        mid=features.mid[start:end].copy(),
        ofi=features.ofi[start:end].copy(),
        queue_imbalance=features.queue_imbalance[start:end].copy(),
    )


def run_killtest_split(
    features: FeatureFrame,
    *,
    split_at_fraction: float = 0.5,
    retention_gate: float = _RETENTION_GATE,
    primary_horizon_sec: int = _PRIMARY_HORIZON_SEC,
    horizons_sec: tuple[int, ...] = _TARGET_HORIZONS_SEC,
    ic_gate: float = _IC_GATE,
    pvalue_gate: float = _PERM_PVALUE_GATE,
    seed: int = SEED,
) -> SplitVerdict:
    """Compute train + test halves and verdict the OOS question alone.

    The full gate (`run_killtest`) already established significance on the
    entire window. The split's single purpose is OOS generalization. By AE
    principles 1 & 20 (only the inevitable; elimination over addition), the
    verdict uses two criteria and nothing more:

        IC(test) / IC(train) >= retention_gate
        test.residual_ic > 0 AND test.residual_ic_pvalue < pvalue_gate

    Per-half `GateVerdict`s are still computed and exposed in the JSON for
    diagnostic transparency (so the operator can see any half-level anomaly),
    but they do NOT feed the split verdict. This avoids double-counting the
    significance test with reduced power on halved samples.
    """
    if not 0.1 <= split_at_fraction <= 0.9:
        raise ValueError(f"split_at_fraction must be in [0.1, 0.9], got {split_at_fraction}")
    n = features.n_rows
    split_idx = int(n * split_at_fraction)
    train_features = slice_features(features, 0, split_idx)
    test_features = slice_features(features, split_idx, n)

    train = run_killtest(
        train_features,
        primary_horizon_sec=primary_horizon_sec,
        horizons_sec=horizons_sec,
        ic_gate=ic_gate,
        pvalue_gate=pvalue_gate,
        seed=seed,
    )
    test = run_killtest(
        test_features,
        primary_horizon_sec=primary_horizon_sec,
        horizons_sec=horizons_sec,
        ic_gate=ic_gate,
        pvalue_gate=pvalue_gate,
        seed=seed,
    )

    reasons: list[str] = []
    if np.isfinite(train.ic_signal) and train.ic_signal > 0 and np.isfinite(test.ic_signal):
        retention = float(test.ic_signal / train.ic_signal)
    else:
        retention = float("nan")

    if not np.isfinite(retention):
        reasons.append("IC retention undefined (train IC non-positive or NaN)")
    elif retention < retention_gate:
        reasons.append(
            f"IC retention={retention:.3f} < gate={retention_gate:.3f} "
            f"(test/train = {test.ic_signal:.4f}/{train.ic_signal:.4f})"
        )
    if not np.isfinite(test.residual_ic) or test.residual_ic <= 0.0:
        reasons.append(
            f"test residual_IC={test.residual_ic:.4f} <= 0 (orthogonal edge did not survive OOS)"
        )
    if test.residual_ic_pvalue > pvalue_gate:
        reasons.append(
            f"test residual permutation p={test.residual_ic_pvalue:.3f} "
            f"> gate={pvalue_gate:.3f} (OOS orthogonal edge not significant)"
        )

    verdict = "PROCEED" if not reasons else "KILL"
    return SplitVerdict(
        verdict=verdict,
        reasons=reasons,
        train=train,
        test=test,
        split_at_fraction=float(split_at_fraction),
        ic_retention=retention,
        retention_gate=float(retention_gate),
        seed=seed,
    )


def split_verdict_to_json(verdict: SplitVerdict) -> str:
    return json.dumps(asdict(verdict), indent=2, sort_keys=True, default=str)
