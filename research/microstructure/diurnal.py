"""Diurnal profile of the Ricci cross-sectional edge.

Folds multiple L2-substrate sessions by UTC hour-of-day (0..23) and computes
per-hour pooled Spearman IC against forward mid-return. Designed to falsify
or confirm the preliminary sign-flip hypothesis raised by Session-2
(Fri 20-22Z showed IC≈-0.2 against Session-1 Fri 08-13Z IC≈+0.12).

Binary output contract:

    SIGN_FLIP_CONFIRMED   — at least one hour bucket has IC significantly
                            negative (p < gate) AND at least one other
                            bucket has IC significantly positive, both
                            with n_rows >= min_rows.
    SIGN_STABLE           — all significant hour buckets share sign.
    UNDERPOWERED          — no hour has n_rows >= min_rows.

No numerical overlap with existing gates. Pure read-side analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.stats import spearmanr

from research.microstructure.killtest import (
    FeatureFrame,
    cross_sectional_ricci_signal,
)

_HORIZON_SEC_DEFAULT: int = 180
_MIN_ROWS_PER_HOUR_DEFAULT: int = 300
_PERM_TRIALS_DEFAULT: int = 500
_PVALUE_GATE_DEFAULT: float = 0.05
_SEED_DEFAULT: int = 42


def utc_hour_of_row(start_ms: int, n_rows: int) -> NDArray[np.int64]:
    """Return UTC hour-of-day (0..23) for each consecutive 1-second row.

    The caller supplies the start epoch-ms of row 0; subsequent rows are
    assumed to be one-second apart (killtest.FeatureFrame grid convention).
    """
    if n_rows < 0:
        raise ValueError(f"n_rows must be >= 0, got {n_rows}")
    start_s = int(start_ms) // 1000
    seconds = start_s + np.arange(n_rows, dtype=np.int64)
    hours = (seconds // 3600) % 24
    return hours


@dataclass(frozen=True)
class HourBucket:
    hour_utc: int
    n_rows: int
    ic_signal: float
    residual_ic: float
    permutation_p: float
    session_source: tuple[str, ...]


@dataclass
class DiurnalProfile:
    verdict: str
    reasons: list[str]
    horizon_sec: int
    min_rows_per_hour: int
    pvalue_gate: float
    hour_buckets: dict[int, HourBucket] = field(default_factory=dict)
    n_significant_positive: int = 0
    n_significant_negative: int = 0
    sessions_used: tuple[str, ...] = ()


def _forward_log_return(mid: NDArray[np.float64], horizon_rows: int) -> NDArray[np.float64]:
    log_mid = np.log(mid)
    fwd = np.full_like(log_mid, np.nan, dtype=np.float64)
    if horizon_rows >= log_mid.shape[0]:
        return fwd
    fwd[:-horizon_rows] = log_mid[horizon_rows:] - log_mid[:-horizon_rows]
    return fwd


def _pooled_spearman(s_flat: NDArray[np.float64], t_flat: NDArray[np.float64]) -> float:
    mask = np.isfinite(s_flat) & np.isfinite(t_flat)
    if int(mask.sum()) < 50:
        return float("nan")
    s = s_flat[mask]
    t = t_flat[mask]
    if float(np.std(s)) < 1e-14 or float(np.std(t)) < 1e-14:
        return float("nan")
    rho, _ = spearmanr(s, t)
    return float(rho) if np.isfinite(rho) else float("nan")


def _permutation_pvalue(
    signal_flat: NDArray[np.float64],
    target_flat: NDArray[np.float64],
    observed: float,
    *,
    trials: int,
    seed: int,
) -> float:
    if not np.isfinite(observed):
        return 1.0
    rng = np.random.default_rng(seed)
    count = 0
    done = 0
    mask = np.isfinite(signal_flat) & np.isfinite(target_flat)
    s = signal_flat[mask]
    t = target_flat[mask]
    if s.size < 50:
        return 1.0
    for _ in range(trials):
        perm = rng.permutation(s.size)
        ic = _pooled_spearman(s[perm], t)
        if not np.isfinite(ic):
            continue
        if abs(ic) >= abs(observed):
            count += 1
        done += 1
    if done == 0:
        return 1.0
    return (count + 1) / (done + 1)


def _per_session_bucket_arrays(
    features: FeatureFrame,
    horizon_sec: int,
    start_ms: int,
) -> tuple[NDArray[np.int64], NDArray[np.float64], NDArray[np.float64]]:
    """Return (hour_of_row, signal_flat, target_flat) for one session.

    signal_flat has shape (n_rows * n_symbols,), broadcast from the
    cross-sectional 1d signal. target_flat is the corresponding forward
    log-return panel, flattened in the same order. Hour-of-row is the
    UTC hour assigned to row index (applies to all symbols of that row).
    """
    n_rows = features.n_rows
    signal_1d = cross_sectional_ricci_signal(features.ofi)
    signal_panel = np.repeat(signal_1d[:, None], features.n_symbols, axis=1)
    target = _forward_log_return(features.mid, horizon_sec)
    hour_of_row = utc_hour_of_row(start_ms, n_rows)
    hour_panel = np.repeat(hour_of_row[:, None], features.n_symbols, axis=1)
    return (
        hour_panel.ravel(),
        signal_panel.ravel(),
        target.ravel(),
    )


def compute_diurnal_profile(
    sessions: list[tuple[str, FeatureFrame, int]],
    *,
    horizon_sec: int = _HORIZON_SEC_DEFAULT,
    min_rows_per_hour: int = _MIN_ROWS_PER_HOUR_DEFAULT,
    perm_trials: int = _PERM_TRIALS_DEFAULT,
    pvalue_gate: float = _PVALUE_GATE_DEFAULT,
    seed: int = _SEED_DEFAULT,
) -> DiurnalProfile:
    """Fold multiple sessions by UTC hour and emit per-hour IC + verdict.

    Each session tuple: (session_name, feature_frame, session_start_ms).
    """
    if not sessions:
        return DiurnalProfile(
            verdict="UNDERPOWERED",
            reasons=["no sessions provided"],
            horizon_sec=horizon_sec,
            min_rows_per_hour=min_rows_per_hour,
            pvalue_gate=pvalue_gate,
            sessions_used=(),
        )

    hour_to_signal: dict[int, list[NDArray[np.float64]]] = {}
    hour_to_target: dict[int, list[NDArray[np.float64]]] = {}
    hour_to_sources: dict[int, set[str]] = {}

    for name, features, start_ms in sessions:
        hour_panel, signal_flat, target_flat = _per_session_bucket_arrays(
            features, horizon_sec, start_ms
        )
        for h in range(24):
            mask = hour_panel == h
            if not bool(mask.any()):
                continue
            hour_to_signal.setdefault(h, []).append(signal_flat[mask])
            hour_to_target.setdefault(h, []).append(target_flat[mask])
            hour_to_sources.setdefault(h, set()).add(name)

    buckets: dict[int, HourBucket] = {}
    n_pos = 0
    n_neg = 0
    for h in sorted(hour_to_signal.keys()):
        s = np.concatenate(hour_to_signal[h])
        t = np.concatenate(hour_to_target[h])
        n_finite = int((np.isfinite(s) & np.isfinite(t)).sum())
        if n_finite < min_rows_per_hour:
            buckets[h] = HourBucket(
                hour_utc=h,
                n_rows=n_finite,
                ic_signal=float("nan"),
                residual_ic=float("nan"),
                permutation_p=float("nan"),
                session_source=tuple(sorted(hour_to_sources[h])),
            )
            continue
        ic = _pooled_spearman(s, t)
        p = _permutation_pvalue(s, t, ic, trials=perm_trials, seed=seed + h)
        buckets[h] = HourBucket(
            hour_utc=h,
            n_rows=n_finite,
            ic_signal=ic,
            residual_ic=float("nan"),  # residualization at per-hour level is out of scope v1
            permutation_p=p,
            session_source=tuple(sorted(hour_to_sources[h])),
        )
        if np.isfinite(ic) and p < pvalue_gate:
            if ic > 0.0:
                n_pos += 1
            elif ic < 0.0:
                n_neg += 1

    reasons: list[str] = []
    if not buckets:
        verdict = "UNDERPOWERED"
        reasons.append("no hour buckets produced")
    elif n_pos + n_neg == 0:
        verdict = "UNDERPOWERED"
        reasons.append(
            f"no significant hour at p<{pvalue_gate}: "
            f"{sum(1 for b in buckets.values() if b.n_rows >= min_rows_per_hour)} "
            f"buckets had n>={min_rows_per_hour}"
        )
    elif n_pos > 0 and n_neg > 0:
        verdict = "SIGN_FLIP_CONFIRMED"
        reasons.append(f"{n_pos} positive + {n_neg} negative hours significant at p<{pvalue_gate}")
    else:
        verdict = "SIGN_STABLE"
        sign = "positive" if n_pos > 0 else "negative"
        reasons.append(
            f"all {n_pos + n_neg} significant hours are {sign}; no sign flip in sampled diurnal window"
        )

    return DiurnalProfile(
        verdict=verdict,
        reasons=reasons,
        horizon_sec=horizon_sec,
        min_rows_per_hour=min_rows_per_hour,
        pvalue_gate=pvalue_gate,
        hour_buckets=buckets,
        n_significant_positive=n_pos,
        n_significant_negative=n_neg,
        sessions_used=tuple(name for name, _, _ in sessions),
    )


def profile_to_json_dict(profile: DiurnalProfile) -> dict[str, Any]:
    """Serialize DiurnalProfile to a plain JSON-ready dict."""
    return {
        "verdict": profile.verdict,
        "reasons": list(profile.reasons),
        "horizon_sec": profile.horizon_sec,
        "min_rows_per_hour": profile.min_rows_per_hour,
        "pvalue_gate": profile.pvalue_gate,
        "n_significant_positive": profile.n_significant_positive,
        "n_significant_negative": profile.n_significant_negative,
        "sessions_used": list(profile.sessions_used),
        "hour_buckets": {
            str(h): {
                "hour_utc": b.hour_utc,
                "n_rows": b.n_rows,
                "ic_signal": (float(b.ic_signal) if np.isfinite(b.ic_signal) else None),
                "permutation_p": (float(b.permutation_p) if np.isfinite(b.permutation_p) else None),
                "session_source": list(b.session_source),
            }
            for h, b in profile.hour_buckets.items()
        },
    }


def session_start_ms_from_frames(frames: dict[str, pd.DataFrame]) -> int:
    """Helper: extract the earliest ts_event across symbol frames (ms).

    Mirrors build_feature_frame's computation of start_ms: it's the max
    of per-symbol first ts_event (because BFR uses overlap start). Keeps
    the diurnal hour attribution aligned with the FeatureFrame row-0.
    """
    if not frames:
        raise ValueError("no symbol frames provided")
    return int(max(int(df["ts_event"].iloc[0]) for df in frames.values()))
