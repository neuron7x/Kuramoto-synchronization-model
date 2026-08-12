# mypy: disable-error-code="unused-ignore"
"""Historical signal backfill generator.

Reads Exness tick data via efinance, runs GeoSync physics kernel
on rolling windows, writes to Parquet and optionally QuestDB.

Usage:
  python -m coherence_bridge.backfill \
    --instruments EURUSD GBPUSD \
    --start 2024-01-01 --end 2024-07-01 \
    --output backfill.parquet --questdb-host localhost
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from typing import Any

import numpy as np
import pandas as pd

from coherence_bridge.questdb_writer import QuestDBSignalWriter
from coherence_bridge.risk import compute_risk_scalar

logger = logging.getLogger("coherence_bridge.backfill")

GEOSYNC_PATH = os.getenv("GEOSYNC_PATH", "")

_PHASE_TO_REGIME: dict[str, str] = {
    "CHAOTIC": "DECOHERENT",
    "PROTO_EMERGENT": "METASTABLE",
    "STRONG_EMERGENT": "COHERENT",
    "TRANSITION": "CRITICAL",
    "POST_EMERGENT": "DECOHERENT",
}


def download_tick_data(instrument: str, start: str, end: str) -> pd.DataFrame:
    """Download tick data from Exness via efinance."""
    try:
        from exfinance import Exness  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "efinance not installed. "
            "git clone https://github.com/alihaskar/efinance && cd efinance && poetry install"
        ) from exc
    result: pd.DataFrame = Exness().download(instrument, start, end)
    return result


def _ensure_geosync() -> None:
    if GEOSYNC_PATH not in sys.path:
        sys.path.insert(0, GEOSYNC_PATH)


def compute_signals_on_window(
    df: pd.DataFrame,
    instrument: str,
    window_size: int = 300,
    step_size: int = 60,
) -> list[dict[str, object]]:
    """Run GeoSync physics kernel on rolling windows.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with DatetimeIndex and 'close', 'volume' columns.
    instrument : str
        Instrument name for the output signal.
    window_size : int
        Bars per compute window.
    step_size : int
        Bars to advance between windows.
    """
    _ensure_geosync()
    from core.indicators.kuramoto_ricci_composite import GeoSyncCompositeEngine
    from core.metrics.aperiodic import aperiodic_slope
    from core.physics.forman_ricci import FormanRicciCurvature
    from core.physics.lyapunov_exponent import maximal_lyapunov_exponent

    engine: Any = GeoSyncCompositeEngine()
    forman: Any = FormanRicciCurvature()
    signals: list[dict[str, object]] = []
    seq = 0
    last_regime = "UNKNOWN"
    regime_start = time.time()

    for start_idx in range(0, len(df) - window_size + 1, step_size):
        window = df.iloc[start_idx : start_idx + window_size]
        prices = np.asarray(window["close"].values, dtype=np.float64)
        returns = np.diff(np.log(prices + 1e-12))

        if len(returns) < 30:
            continue

        # Composite analysis
        try:
            composite = engine.analyze_market(window)
        except Exception as exc:
            logger.debug("Composite failed at idx %d: %s", start_idx, exc)
            continue

        # gamma — DERIVED from PSD
        raw_slope = aperiodic_slope(returns, fs=1.0, f_lo=0.001, f_hi=0.5)
        gamma = abs(raw_slope) if (math.isfinite(raw_slope) and raw_slope != 0.0) else 1.0

        # Forman-Ricci
        n_lags = min(5, len(returns) // 10)
        if n_lags >= 2:
            lagged = np.column_stack(
                [returns[i : len(returns) - n_lags + i + 1] for i in range(n_lags)]
            )
            try:
                ricci_result = forman.compute_from_prices(lagged, window=min(30, len(lagged)))
                ricci_curvature = ricci_result.kappa_mean
            except Exception:
                ricci_curvature = composite.static_ricci
        else:
            ricci_curvature = composite.static_ricci

        # Lyapunov
        if len(returns) >= 50:
            lyap = maximal_lyapunov_exponent(returns, dim=3, tau=1)
            if not math.isfinite(lyap):
                lyap = 0.0
        else:
            lyap = 0.0

        regime = _PHASE_TO_REGIME.get(composite.phase.name, "UNKNOWN")
        if regime != last_regime:
            regime_start = time.time()
            last_regime = regime

        signal_strength = max(
            -1.0,
            min(
                1.0,
                composite.entry_signal - composite.exit_signal,
            ),
        )

        seq += 1
        signals.append(
            {
                "timestamp_ns": int(window.index[-1].timestamp() * 1e9),
                "instrument": instrument,
                "gamma": round(float(gamma), 6),
                "order_parameter_R": round(float(composite.kuramoto_R), 6),
                "ricci_curvature": round(float(ricci_curvature), 6),
                "lyapunov_max": round(float(lyap), 6),
                "regime": regime,
                "regime_confidence": round(float(composite.confidence), 4),
                "regime_duration_s": round(time.time() - regime_start, 2),
                "signal_strength": round(float(signal_strength), 4),
                "risk_scalar": round(compute_risk_scalar(gamma, fail_closed=True), 4),
                "sequence_number": seq,
            }
        )

    return signals


def main() -> None:
    parser = argparse.ArgumentParser(description="CoherenceBridge historical backfill")
    parser.add_argument("--instruments", nargs="+", default=["EURUSD"])
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--output", default="backfill.parquet", help="Output Parquet path")
    parser.add_argument("--questdb-host", default=None)
    parser.add_argument("--questdb-port", type=int, default=9000)
    args = parser.parse_args()

    all_signals: list[dict[str, object]] = []
    for inst in args.instruments:
        logger.info("Downloading %s %s -> %s...", inst, args.start, args.end)
        ticks = download_tick_data(inst, args.start, args.end)
        logger.info("  %d ticks downloaded", len(ticks))
        signals = compute_signals_on_window(ticks, inst)
        all_signals.extend(signals)
        logger.info("  %d signal points generated", len(signals))

    df = pd.DataFrame(all_signals)
    df.to_parquet(args.output, engine="pyarrow")
    logger.info("Wrote %d signals to %s", len(df), args.output)

    if args.questdb_host:
        writer = QuestDBSignalWriter(args.questdb_host, args.questdb_port)
        df["timestamp"] = pd.to_datetime(df["timestamp_ns"], unit="ns")
        writer.write_dataframe(df)
        logger.info("QuestDB write complete")


if __name__ == "__main__":
    main()
