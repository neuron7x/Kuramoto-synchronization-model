"""Regime-signal primitives — data loading, Kuramoto R(t), 3-state regime.

Copy-ported from ``~/spikes/cross_asset_sync_regime/sync_regime.py`` with
type annotations added. Numerics are preserved bit-for-bit against the
spike; invariants are enforced at module boundary. The closed-family
identifier is not referenced here (test_module_boundary asserts this).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from scipy.signal import hilbert

from .invariants import CAKInvariantError

_REGIME_CACHE_MAP: dict[str, str] = {
    "BTC": "btc_usdt_1d",
    "ETH": "eth_usdt_1d",
    "SPY": "spy_1d",
    "QQQ": "qqq_1d",
    "GLD": "gld_1d",
    "TLT": "tlt_1d",
    "DXY": "dxy_1d",
    "VIX": "vix_1d",
}


def _default_cache_map() -> dict[str, str]:
    """Read-only copy of the spike cache mapping."""
    return dict(_REGIME_CACHE_MAP)


def _utc_index(idx: pd.Index) -> pd.DatetimeIndex:
    """Coerce a DatetimeIndex-compatible index to UTC."""
    dt_idx = cast(pd.DatetimeIndex, idx)
    if dt_idx.tz is None:
        return dt_idx.tz_localize("UTC")
    return dt_idx.tz_convert("UTC")


def load_asset_close(
    name: str,
    data_dir: Path,
    cache_map: Mapping[str, str] | None = None,
) -> pd.Series:
    """Load a single asset's ``close`` series, UTC-localized.

    Mirrors ``sync_regime.load_asset`` and ``backtest_v2.load_asset_close``:
    reads CSV with ``timestamp`` column as the index, localises to UTC
    if naïve, converts to UTC otherwise. Returns the ``close`` column
    renamed to ``name``.
    """
    cmap: Mapping[str, str] = cache_map if cache_map is not None else _REGIME_CACHE_MAP
    if name not in cmap:
        raise CAKInvariantError(f"asset {name!r} not in cache_map keys")
    path = data_dir / f"{cmap[name]}.csv"
    if not path.is_file():
        raise CAKInvariantError(f"data file missing for {name}: {path}")
    df = pd.read_csv(path, index_col="timestamp", parse_dates=True)
    df.index = _utc_index(df.index)
    series: pd.Series = df["close"].rename(name).astype(float)
    return series


def _align_panel(closes: pd.DataFrame, ffill_limit_bdays: int) -> pd.DataFrame:
    if closes.empty:
        raise CAKInvariantError("empty panel after concat")
    bdays = pd.date_range(
        start=closes.index.min(),
        end=closes.index.max(),
        freq="B",
        tz="UTC",
    )
    closes = closes.reindex(bdays).ffill(limit=ffill_limit_bdays)
    closes = closes.dropna()
    if closes.empty:
        raise CAKInvariantError("empty panel after ffill+dropna")
    return closes


def build_panel(
    assets: list[str] | tuple[str, ...],
    data_dir: Path,
    ffill_limit_bdays: int,
    cache_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Build the aligned daily close panel (regime universe)."""
    series_list = [load_asset_close(a, data_dir, cache_map) for a in assets]
    panel = pd.concat(series_list, axis=1, sort=False)
    return _align_panel(panel, ffill_limit_bdays)


def build_returns_panel(
    assets: list[str] | tuple[str, ...],
    data_dir: Path,
    ffill_limit_bdays: int,
    cache_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Strategy-side log-return panel (subset of assets)."""
    closes = pd.concat(
        [load_asset_close(a, data_dir, cache_map) for a in assets],
        axis=1,
        sort=False,
    )
    closes = _align_panel(closes, ffill_limit_bdays)
    ratio = closes / closes.shift(1)
    log_ret = cast(pd.DataFrame, np.log(ratio))
    return log_ret.dropna()


def compute_log_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Element-wise log returns with first row dropped."""
    ratio = panel / panel.shift(1)
    log_ret = cast(pd.DataFrame, np.log(ratio))
    return log_ret.dropna()


def _detrend_series(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling-mean detrending; first ``window - 1`` values become NaN."""
    s = pd.Series(x)
    trend = s.rolling(window=window, min_periods=window).mean()
    return (s - trend).to_numpy()


def extract_phase(log_returns: pd.DataFrame, detrend_window: int) -> pd.DataFrame:
    """Instantaneous phase via Hilbert transform on detrended log returns.

    Preserves the spike's mask handling: if fewer than
    ``detrend_window + 10`` finite values remain, raise.
    """
    out_cols: dict[str, np.ndarray] = {}
    for col in log_returns.columns:
        x = log_returns[col].to_numpy()
        x_detrend = _detrend_series(x, detrend_window)
        mask = np.isfinite(x_detrend)
        if mask.sum() < detrend_window + 10:
            raise CAKInvariantError(f"insufficient detrended data for {col}")
        analytic = np.full_like(x_detrend, np.nan, dtype=np.complex128)
        analytic[mask] = hilbert(x_detrend[mask])
        out_cols[str(col)] = np.angle(analytic)
    phases = pd.DataFrame(out_cols, index=log_returns.index).astype(float)
    return phases


def kuramoto_order(phases: pd.DataFrame, window: int) -> pd.Series:
    """Rolling Kuramoto order parameter R(t).

    Two-step construction: instantaneous cross-asset sync
    :math:`R_{\\text{inst}}(t) = |\\frac{1}{N}\\sum_k e^{i\\varphi_k(t)}|`,
    then rolling mean over ``window`` bars for smoothing. INV-K1 / CAK3:
    :math:`0 \\le R(t) \\le 1` by construction.
    """
    arr = phases.to_numpy()
    mask = np.isfinite(arr)
    if not mask.all():
        raise CAKInvariantError("INV-HPC2: non-finite phases passed to kuramoto_order")
    z = np.exp(1j * arr)
    r_inst = np.abs(z.mean(axis=1))
    s = pd.Series(r_inst, index=phases.index, name="R")
    rolled: pd.Series = s.rolling(window=window, min_periods=window).mean()
    return rolled


def classify_regimes(
    r_series: pd.Series,
    train_frac: float,
    q_low: float,
    q_high: float,
) -> pd.Series:
    """Three-state regime classification from R(t).

    Quantile thresholds (``q_low`` → low-sync cutoff, ``q_high`` →
    high-sync cutoff) are fit on the first ``train_frac`` fraction of
    the non-NaN R values and held fixed for the whole series.
    """
    clean = r_series.dropna()
    if clean.empty:
        raise CAKInvariantError("R series is empty; cannot classify regimes")
    split = int(len(clean) * train_frac)
    if split < 50:
        raise CAKInvariantError(
            f"train split {split} too small (need at least 50 bars for q-quantile fit)"
        )
    calib = clean.iloc[:split]
    q33 = float(calib.quantile(q_low))
    q66 = float(calib.quantile(q_high))
    labels: list[str] = []
    for val in r_series.to_numpy():
        if not np.isfinite(val):
            labels.append("unknown")
        elif val <= q33:
            labels.append("low_sync")
        elif val <= q66:
            labels.append("mid_sync")
        else:
            labels.append("high_sync")
    regimes = pd.Series(labels, index=r_series.index, dtype="object", name="regime")
    regimes.attrs["q33"] = q33
    regimes.attrs["q66"] = q66
    return regimes


def as_metadata(panel: pd.DataFrame, r_series: pd.Series) -> dict[str, Any]:
    """Serialisable panel summary for audit trail."""
    r_clean = r_series.dropna()
    return {
        "n_bdays": int(len(panel)),
        "first_ts": str(panel.index[0]),
        "last_ts": str(panel.index[-1]),
        "r_first_ts": str(r_clean.index[0]),
        "r_last_ts": str(r_clean.index[-1]),
        "r_min": float(r_series.min()),
        "r_max": float(r_series.max()),
        "r_mean": float(r_series.mean()),
    }
