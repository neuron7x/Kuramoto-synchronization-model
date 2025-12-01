"""Multi-scale Kuramoto synchronization analyzer for market microstructure.

This module implements a hierarchical Kuramoto oscillator model that analyzes market
synchronization patterns across multiple time horizons. It leverages phase coherence
of price oscillations to detect emergent market structures and regime shifts.

The Kuramoto model treats each timeframe as a coupled oscillator. When oscillators
synchronize (high order parameter R), it indicates strong market consensus and
directional movement. Cross-scale coherence measures how well different timeframes
align, providing insight into the robustness of market trends.

Key Components:
    TimeFrame: Enumeration of standard trading horizons (1m, 5m, 15m, 1h)
    KuramotoResult: Per-timeframe synchronization metrics
    MultiScaleResult: Aggregated consensus across all analyzed timeframes
    FractalResampler: Efficient hierarchical data resampling with caching
    MultiScaleKuramoto: Main analyzer class for computing order parameters

The implementation includes energy-aware caching to minimize computational overhead
during backtesting and supports adaptive windowing for different market conditions.

Example:
    >>> analyzer = MultiScaleKuramoto()
    >>> result = analyzer.analyze(price_df)
    >>> print(f"Consensus R: {result.consensus_R:.3f}")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence

import networkx as nx
import numpy as np
import pandas as pd

try:  # SciPy is optional in lightweight environments
    from scipy import signal as _signal
except Exception:  # pragma: no cover - executed when SciPy unavailable
    _signal = None

from . import fractal_gcl as _fractal_gcl
from .base import BaseFeature, FeatureResult
from .cache import FileSystemIndicatorCache, hash_input_data


class TimeFrame(Enum):
    """Discrete trading horizons expressed in seconds."""

    M1 = 60
    M5 = 300
    M15 = 900
    H1 = 3600

    @property
    def pandas_freq(self) -> str:
        """Return the pandas frequency string for resampling."""

        return f"{int(self.value)}s"

    @property
    def seconds(self) -> int:
        """Expose the time frame in seconds for downstream consumers."""

        return int(self.value)

    def __str__(self) -> str:  # pragma: no cover - tiny helper
        return self.name


@dataclass(slots=True)
class KuramotoResult:
    """Per-timeframe Kuramoto order parameter and associated metadata."""

    order_parameter: float
    mean_phase: float
    window: int


@dataclass(slots=True)
class MultiScaleResult:
    """Aggregate multi-scale consensus metrics produced by the analyzer."""

    consensus_R: float
    cross_scale_coherence: float
    dominant_scale: Optional[TimeFrame]
    adaptive_window: int
    timeframe_results: Mapping[TimeFrame, KuramotoResult]
    skipped_timeframes: Sequence[TimeFrame]
    timeframe_endpoints: Mapping[TimeFrame, pd.Timestamp] = field(default_factory=dict)
    timeframe_series: Mapping[TimeFrame, pd.Series] = field(default_factory=dict)
    energy_profile: Mapping[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class FractalResampler:
    """Energy-aware hierarchical resampling cache.

    The resampler memoizes intermediate timeframes and reuses them when a coarser
    horizon is an integer multiple of a previously computed one.  This mirrors
    the "fractal" refinement of horizons used throughout TradePulse and reduces
    redundant :meth:`pandas.Series.resample` calls—cutting CPU time and energy
    consumption in large backtests.
    """

    series: pd.Series
    _cache: MutableMapping[TimeFrame, pd.Series] = field(
        default_factory=dict, init=False
    )
    _cache_hits: int = field(default=0, init=False)
    _direct_resamples: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.series.index, pd.DatetimeIndex):
            raise TypeError("FractalResampler requires a DatetimeIndex")
        # Normalise ordering once; downstream resampling works on monotonic data.
        self.series = self.series.sort_index()

    def resample(self, timeframe: TimeFrame) -> pd.Series:
        cached = self._cache.get(timeframe)
        if cached is not None:
            return cached

        parent = self._select_parent(timeframe)
        if parent is not None:
            base = self._cache[parent]
            self._cache_hits += 1
        else:
            base = self.series
            self._direct_resamples += 1

        resampled = base.resample(timeframe.pandas_freq).last()
        resampled = resampled.ffill().dropna()
        self._cache[timeframe] = resampled
        return resampled

    def resample_many(
        self,
        timeframes: Sequence[TimeFrame],
        *,
        strict: bool = False,
    ) -> Mapping[TimeFrame, pd.Series]:
        """Resample multiple ``timeframes`` while maximising fractal reuse.

        The method sorts the requested timeframes from the finest to the
        coarsest horizon to guarantee that any potential parent timeframe is
        available in the cache before its multiples are computed.  The output
        preserves the original ordering of the unique requests so downstream
        consumers receive deterministic mappings.

        Args:
            timeframes: Collection of horizons to resample.
            strict: Propagate ``ValueError`` from :meth:`resample` when ``True``;
                otherwise failed horizons are silently skipped so callers can
                handle them as "insufficient data" events.

        Returns:
            Mapping of each successfully resampled timeframe to its
            corresponding :class:`pandas.Series`.
        """

        if not timeframes:
            return {}

        unique_order: list[TimeFrame] = []
        seen: set[TimeFrame] = set()
        for timeframe in timeframes:
            if timeframe not in seen:
                unique_order.append(timeframe)
                seen.add(timeframe)

        ordered = sorted(unique_order, key=lambda tf: tf.seconds)
        results: dict[TimeFrame, pd.Series] = {}

        for timeframe in ordered:
            try:
                results[timeframe] = self.resample(timeframe)
            except ValueError:
                if strict:
                    raise
                continue

        return {
            timeframe: results[timeframe]
            for timeframe in unique_order
            if timeframe in results
        }

    def stats(self) -> Mapping[str, float]:
        """Expose cache utilisation metrics for energy profiling."""

        requests = self._cache_hits + self._direct_resamples
        reuse_ratio = (self._cache_hits / requests) if requests else 0.0
        return {
            "resample_requests": float(requests),
            "fractal_cache_hits": float(self._cache_hits),
            "direct_resamples": float(self._direct_resamples),
            "fractal_reuse_ratio": float(reuse_ratio),
            "cached_timeframes": float(len(self._cache)),
        }

    def _select_parent(self, timeframe: TimeFrame) -> Optional[TimeFrame]:
        """Return the finest cached timeframe that evenly divides ``timeframe``."""

        best: Optional[TimeFrame] = None
        for candidate in self._cache:
            if timeframe.seconds % candidate.seconds != 0:
                continue
            if candidate.seconds >= timeframe.seconds:
                continue
            if best is None or candidate.seconds > best.seconds:
                best = candidate
        return best


def _hilbert_phase(series: np.ndarray) -> np.ndarray:
    """Return the instantaneous phase of the provided series.

    The NumPy fallback mirrors SciPy's detrended analytic signal to guarantee
    consistent phase and Kuramoto order outputs regardless of dependency
    availability.

    Optimized with reduced array allocations and in-place operations.
    """

    x = np.ascontiguousarray(series, dtype=np.float64)
    n = x.size
    if n == 0:
        raise ValueError("phase extraction requires at least one sample")

    # Check for non-finite values efficiently
    finite_mask = np.isfinite(x)
    if not finite_mask.all():
        finite = x[finite_mask]
        if finite.size == 0:
            x = np.zeros(n, dtype=np.float64)
        else:
            fill_value = float(np.mean(finite))
            np.putmask(x, ~finite_mask, fill_value)

    if _signal is None:
        # Fallback: leverage FFT-based analytic signal
        if n > 1:
            # Linear detrending using polynomial fit
            idx = np.arange(n, dtype=np.float64)
            coeffs = np.polyfit(idx, x, deg=1)
            np.subtract(x, np.polyval(coeffs, idx), out=x)
        else:
            x = x - float(x.mean())

        X = np.fft.fft(x)
        # Build the Hilbert multiplier in-place
        h = np.zeros(n, dtype=np.float64)
        half_n = n // 2
        if n % 2 == 0:
            h[0] = h[half_n] = 1.0
            h[1:half_n] = 2.0
        else:
            h[0] = 1.0
            h[1 : (n + 1) // 2] = 2.0
        analytic = np.fft.ifft(X * h)
    else:
        detrended = _signal.detrend(x)
        analytic = _signal.hilbert(detrended)

    return np.angle(analytic)


def _kuramoto(phases: np.ndarray) -> tuple[float, float]:
    """Compute Kuramoto order parameter and mean phase."""
    # Compute complex exponential and mean
    complex_mean = np.mean(np.exp(1j * np.asarray(phases, dtype=np.float64)))
    return float(np.abs(complex_mean)), float(np.angle(complex_mean))


class WaveletWindowSelector:
    """Selects an analysis window via wavelet energy concentration.

    Optimized with __slots__ for memory efficiency and cached computations.
    """

    __slots__ = (
        "min_window",
        "max_window",
        "wavelet",
        "levels",
        "max_samples",
        "_fallback_window",
        "_widths_cache",
    )

    def __init__(
        self,
        min_window: int = 64,
        max_window: int = 512,
        *,
        wavelet: str = "ricker",
        levels: int = 16,
        max_samples: int | None = 16_384,
    ) -> None:
        if min_window <= 0 or max_window <= 0:
            raise ValueError("window bounds must be positive")
        if min_window > max_window:
            raise ValueError("min_window must be <= max_window")

        min_window = int(min_window)
        max_window = int(max_window)

        levels = int(levels)
        if levels <= 0:
            raise ValueError("levels must be positive")

        if max_samples is not None and max_samples <= 0:
            raise ValueError("max_samples must be positive when provided")

        self.min_window = min_window
        self.max_window = max_window
        self.wavelet = wavelet
        self.levels = max(2, levels)
        self.max_samples = int(max_samples) if max_samples is not None else None
        self._fallback_window = self._compute_fallback_window()
        self._widths_cache: np.ndarray | None = None

    def _compute_fallback_window(self) -> int:
        # Use faster integer square root approximation
        geometric = math.sqrt(float(self.min_window) * float(self.max_window))
        fallback = int(geometric)
        return max(self.min_window, min(fallback, self.max_window))

    def _candidate_widths(self) -> np.ndarray:
        if self._widths_cache is None:
            widths = np.linspace(
                self.min_window, self.max_window, self.levels, dtype=np.float64
            )
            # Clip and convert to integers in one operation
            widths = np.clip(widths, self.min_window, self.max_window).astype(np.int32)
            widths = np.unique(widths)
            widths = widths[widths > 0]
            if widths.size == 0:
                widths = np.array([self.min_window], dtype=np.int32)
            self._widths_cache = widths
        return self._widths_cache

    def select_window(self, prices: Sequence[float]) -> int:
        if self.max_window > 1_048_576:
            raise ValueError(
                "max_window is excessively large for efficient wavelet analysis"
            )
        if self.levels > 8192:
            raise ValueError(
                "levels is excessively large and could exhaust memory during wavelet selection"
            )
        values = np.ascontiguousarray(prices, dtype=np.float64)
        if values.size == 0:
            raise ValueError("cannot select window from empty price series")
        if self.max_samples is not None and values.size > self.max_samples:
            values = values[-self.max_samples :]
        if _signal is None:
            return self._fallback_window

        widths = self._candidate_widths()
        if widths.size == 0:
            return self.min_window

        try:
            transform = _signal.cwt(values, _signal.ricker, widths)
        except Exception:  # pragma: no cover - SciPy edge cases
            return self._fallback_window

        # Optimized energy computation using einsum
        energy = np.einsum("ij,ij->i", transform, transform)
        best_idx = int(np.argmax(energy))
        best_width = int(widths[best_idx])
        return max(self.min_window, min(best_width, self.max_window))


class MultiScaleKuramoto:
    """Compute Kuramoto synchronization metrics across multiple horizons."""

    def __init__(
        self,
        *,
        timeframes: Sequence[TimeFrame] | None = None,
        base_window: int = 256,
        use_adaptive_window: bool = True,
        min_samples_per_scale: int = 64,
        selector: WaveletWindowSelector | None = None,
    ) -> None:
        if base_window <= 0:
            raise ValueError("base_window must be positive")
        if min_samples_per_scale <= 0:
            raise ValueError("min_samples_per_scale must be positive")

        self.timeframes: tuple[TimeFrame, ...] = tuple(
            timeframes
            or (
                TimeFrame.M1,
                TimeFrame.M5,
                TimeFrame.M15,
                TimeFrame.H1,
            )
        )
        self.base_window = int(base_window)
        self.use_adaptive_window = use_adaptive_window
        self.min_samples_per_scale = int(min_samples_per_scale)
        self.selector = selector or WaveletWindowSelector(
            min_window=max(32, self.base_window // 2),
            max_window=self.base_window * 2,
        )

    # -- exposed for unit tests -------------------------------------------------
    def _kuramoto_order_parameter(self, phases: np.ndarray) -> tuple[float, float]:
        return _kuramoto(np.asarray(phases, dtype=float))

    # ---------------------------------------------------------------------------
    def _resample_prices(self, series: pd.Series, timeframe: TimeFrame) -> pd.Series:
        resampled = series.resample(timeframe.pandas_freq).last()
        return resampled.ffill().dropna()

    def _window_for_series(self, values: np.ndarray) -> int:
        if self.use_adaptive_window:
            return int(self.selector.select_window(values))
        return self.base_window

    def analyze(
        self, df: pd.DataFrame, *, price_col: str = "close"
    ) -> MultiScaleResult:
        if price_col not in df.columns:
            raise KeyError(f"column '{price_col}' not found in dataframe")
        series = df[price_col]
        if not isinstance(series.index, pd.DatetimeIndex):
            raise TypeError("MultiScaleKuramoto requires a DatetimeIndex")
        series = series.sort_index().astype(float)

        resampler = FractalResampler(series)
        timeframe_results: MutableMapping[TimeFrame, KuramotoResult] = {}
        skipped: list[TimeFrame] = []
        windows: list[int] = []
        endpoints: MutableMapping[TimeFrame, pd.Timestamp] = {}
        samples_processed = 0

        analysis_records: dict[TimeFrame, dict[str, Any]] = {}
        ordered = sorted(self.timeframes, key=lambda tf: tf.seconds)
        prefetched = resampler.resample_many(ordered)
        for timeframe in ordered:
            record: dict[str, Any] = {
                "result": None,
                "endpoint": None,
                "samples": 0,
                "series": None,
            }
            sampled = prefetched.get(timeframe)
            if sampled is None:
                record["skipped"] = True
                analysis_records[timeframe] = record
                continue

            if sampled.empty:
                record["skipped"] = True
                analysis_records[timeframe] = record
                continue

            sampled_values = sampled.to_numpy(copy=False)
            phases = _hilbert_phase(sampled_values)
            window = min(self._window_for_series(sampled_values), phases.size)
            if window < self.min_samples_per_scale:
                record["skipped"] = True
                analysis_records[timeframe] = record
                continue

            R, psi = self._kuramoto_order_parameter(phases[-window:])
            record.update(
                {
                    "result": KuramotoResult(
                        order_parameter=R, mean_phase=psi, window=window
                    ),
                    "endpoint": sampled.index[-1],
                    "samples": int(sampled.size),
                    "series": sampled,
                    "skipped": False,
                }
            )
            analysis_records[timeframe] = record

        accounted_for_samples: set[TimeFrame] = set()
        timeframe_series: dict[TimeFrame, pd.Series] = {}
        for timeframe in self.timeframes:
            record = analysis_records.get(timeframe)
            if not record or record.get("skipped", False):
                skipped.append(timeframe)
                continue
            result = record["result"]
            if result is None:
                skipped.append(timeframe)
                continue
            timeframe_results[timeframe] = result
            windows.append(result.window)
            endpoint = record["endpoint"]
            if endpoint is not None:
                endpoints[timeframe] = endpoint
            if timeframe not in accounted_for_samples:
                samples_processed += int(record.get("samples", 0))
                accounted_for_samples.add(timeframe)
            series = record.get("series")
            if isinstance(series, pd.Series):
                timeframe_series[timeframe] = series

        if timeframe_results:
            R_values = np.array(
                [res.order_parameter for res in timeframe_results.values()], dtype=float
            )
            consensus_R = float(np.mean(R_values))
            if R_values.size > 1:
                dispersion = float(np.std(R_values))
                cross_scale_coherence = float(np.clip(1.0 - dispersion, 0.0, 1.0))
            else:
                cross_scale_coherence = 1.0
            dominant_scale = max(
                timeframe_results.items(),
                key=lambda item: item[1].order_parameter,
            )[0]
        else:
            consensus_R = 0.0
            cross_scale_coherence = 0.0
            dominant_scale = None

        adaptive_window = (
            int(np.median(windows))
            if windows and self.use_adaptive_window
            else self.base_window
        )

        energy_profile = {
            **resampler.stats(),
            "samples_processed": float(samples_processed),
        }

        return MultiScaleResult(
            consensus_R=consensus_R,
            cross_scale_coherence=cross_scale_coherence,
            dominant_scale=dominant_scale,
            adaptive_window=adaptive_window,
            timeframe_results=dict(timeframe_results),
            skipped_timeframes=tuple(skipped),
            timeframe_endpoints=dict(endpoints),
            timeframe_series=dict(timeframe_series),
            energy_profile=energy_profile,
        )


class MultiScaleKuramotoFeature(BaseFeature):
    """Feature wrapper exposing multi-scale Kuramoto consensus as a metric."""

    def __init__(
        self,
        analyzer: MultiScaleKuramoto | None = None,
        *,
        name: str | None = None,
        cache: FileSystemIndicatorCache | None = None,
    ) -> None:
        super().__init__(name or "multi_scale_kuramoto")
        self.analyzer = analyzer or MultiScaleKuramoto()
        self.cache = cache

    def _selector_params(self) -> Mapping[str, Any]:
        selector = getattr(self.analyzer, "selector", None)
        if selector is None:
            return {}
        params: dict[str, Any] = {"class": selector.__class__.__name__}
        for attr in ("min_window", "max_window", "wavelet", "levels", "max_samples"):
            if hasattr(selector, attr):
                params[attr] = getattr(selector, attr)
        return params

    def _cache_params(self, price_col: str) -> Mapping[str, Any]:
        timeframes = getattr(self.analyzer, "timeframes", ())
        base_window = getattr(self.analyzer, "base_window", None)
        use_adaptive = getattr(self.analyzer, "use_adaptive_window", None)
        min_samples = getattr(self.analyzer, "min_samples_per_scale", None)
        params: dict[str, Any] = {
            "timeframes": [tf.name for tf in timeframes] if timeframes else [],
            "price_col": price_col,
            "selector": self._selector_params(),
        }
        if base_window is not None:
            params["base_window"] = base_window
        if use_adaptive is not None:
            params["use_adaptive_window"] = use_adaptive
        if min_samples is not None:
            params["min_samples_per_scale"] = min_samples
        return params

    @staticmethod
    def _metadata_from_result(result: MultiScaleResult) -> Dict[str, object]:
        metadata: Dict[str, object] = {
            "adaptive_window": result.adaptive_window,
            "timeframes": [tf.name for tf in result.timeframe_results.keys()],
            "skipped_timeframes": [tf.name for tf in result.skipped_timeframes],
        }
        for tf, res in result.timeframe_results.items():
            metadata[f"R_{tf.name}"] = res.order_parameter
            metadata[f"phase_{tf.name}"] = res.mean_phase
            metadata[f"window_{tf.name}"] = res.window
        if result.dominant_scale is not None:
            metadata["dominant_timeframe"] = result.dominant_scale.name
        metadata["cross_scale_coherence"] = result.cross_scale_coherence
        metadata["energy_profile"] = dict(result.energy_profile)
        return metadata

    def _store_timeframe_cache(
        self,
        df: pd.DataFrame,
        price_col: str,
        params: Mapping[str, Any],
        result: MultiScaleResult,
    ) -> None:
        if self.cache is None:
            return

        price_series = df[price_col]
        for timeframe, tf_result in result.timeframe_results.items():
            sampled = result.timeframe_series.get(timeframe)
            if sampled is None:
                sampled = self.analyzer._resample_prices(price_series, timeframe)
            if sampled.empty:
                continue
            timeframe_hash = hash_input_data(sampled.to_frame(name=price_col))
            coverage_start = sampled.index[0].to_pydatetime()
            coverage_end = sampled.index[-1].to_pydatetime()
            fingerprint = self.cache.store(
                indicator_name=f"{self.name}:{timeframe.name}",
                params={
                    **params,
                    "timeframe": timeframe.name,
                    "window": tf_result.window,
                },
                data_hash=timeframe_hash,
                value=tf_result,
                timeframe=timeframe,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                metadata={
                    "order_parameter": tf_result.order_parameter,
                    "mean_phase": tf_result.mean_phase,
                    "window": tf_result.window,
                },
            )
            self.cache.update_backfill_state(
                timeframe,
                last_timestamp=coverage_end,
                fingerprint=fingerprint,
                extras={
                    "records": int(sampled.size),
                    "coverage_start": coverage_start.isoformat(),
                    "coverage_end": coverage_end.isoformat(),
                },
            )

    def transform(self, data: pd.DataFrame, **kwargs: object) -> FeatureResult:
        price_col = kwargs.get("price_col", "close")
        if not isinstance(price_col, str):
            price_col = "close"

        df = data.sort_index()
        params = self._cache_params(price_col)
        cached_result: MultiScaleResult | None = None
        latest_timestamp = None
        if isinstance(df.index, pd.DatetimeIndex) and not df.empty:
            latest_timestamp = df.index[-1].to_pydatetime()

        if self.cache is not None and not df.empty:
            target = df[[price_col]] if price_col in df.columns else df
            data_hash = hash_input_data(target)
            record = self.cache.load(
                indicator_name=self.name,
                params=params,
                data_hash=data_hash,
                timeframe=None,
            )
            if record is not None and (
                latest_timestamp is None
                or record.coverage_end is None
                or record.coverage_end >= latest_timestamp
            ):
                cached_result = record.value

        if cached_result is None:
            result = self.analyzer.analyze(df, price_col=price_col)
        else:
            result = cached_result

        metadata = self._metadata_from_result(result)
        feature = FeatureResult(
            name=self.name, value=result.consensus_R, metadata=metadata
        )

        if self.cache is not None and cached_result is None and not df.empty:
            target = df[[price_col]] if price_col in df.columns else df
            data_hash = hash_input_data(target)
            coverage_start = df.index[0].to_pydatetime()
            coverage_end = df.index[-1].to_pydatetime()
            self.cache.store(
                indicator_name=self.name,
                params=params,
                data_hash=data_hash,
                value=result,
                timeframe=None,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                metadata=metadata,
            )
            self._store_timeframe_cache(df, price_col, params, result)

        return feature


def multiscale_kuramoto(phases: np.ndarray, K: float = 1.0) -> float:
    """Return the Kuramoto order parameter for a batch of phase observations."""

    if K <= 0:
        raise ValueError("K must be positive")
    phase_array = np.asarray(phases, dtype=float)
    if phase_array.size == 0:
        return 0.0
    order = np.exp(1j * phase_array)
    order_parameter = np.abs(np.mean(order))
    return float(order_parameter)


def fractal_gcl_novelty(
    graph: nx.Graph,
    embeddings_i: np.ndarray,
    embeddings_j: np.ndarray,
) -> tuple[float, float]:
    """Convenience wrapper exposing fractal novelty estimates to FHMC."""

    return _fractal_gcl.fractal_gcl_novelty(graph, embeddings_i, embeddings_j)


__all__ = [
    "MultiScaleKuramoto",
    "MultiScaleKuramotoFeature",
    "MultiScaleResult",
    "KuramotoResult",
    "TimeFrame",
    "WaveletWindowSelector",
    "FractalResampler",
    "multiscale_kuramoto",
    "fractal_gcl_novelty",
]


def analyze_simple(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    window: int = 128,
) -> MultiScaleResult:
    """Legacy helper retained for backwards compatibility in smoke tests."""

    analyzer = MultiScaleKuramoto(
        use_adaptive_window=False,
        base_window=window,
        min_samples_per_scale=min(window, 64),
    )
    return analyzer.analyze(df, price_col=price_col)
