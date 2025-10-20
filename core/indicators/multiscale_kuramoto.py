from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, Sequence
from typing import Literal

import numpy as np
import pandas as pd

try:  # SciPy is optional in lightweight environments
    from scipy import signal as _signal
except Exception:  # pragma: no cover - executed when SciPy unavailable
    _signal = None

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
    energy_profile: Mapping[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class FractalResamplerConfig:
    """Configuration knobs for :class:`FractalResampler`.

    Attributes:
        aggregator: Aggregation strategy passed to :meth:`pandas.Series.resample`.
            Accepts the name of a built-in reducer (``"last"`` by default) or a
            callable.  The callable must return a scalar for every bucket so the
            resulting object remains a :class:`pandas.Series`.
        fill_method: Forward/backward fill policy applied after aggregation.
            ``None`` disables filling and mirrors the raw resampled output.  A
            callable can be supplied for bespoke filling logic.
        fill_limit: Optional limit passed to :meth:`pandas.Series.fillna` when a
            string ``fill_method`` is used.
        min_fraction: When greater than zero, enforces a minimum coverage ratio
            (non-null samples / total samples).  Falling below the threshold
            raises :class:`ValueError` so upstream analyzers can mark the
            timeframe as skipped.
    """

    aggregator: str | Callable[[pd.Series], float] = "last"
    fill_method: Literal["ffill", "bfill"] | None | Callable[[pd.Series], pd.Series] = "ffill"
    fill_limit: int | None = None
    min_fraction: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.aggregator, str) and not self.aggregator:
            raise ValueError("aggregator must be a non-empty string")
        if self.fill_limit is not None and self.fill_limit <= 0:
            raise ValueError("fill_limit must be positive when provided")
        if not 0.0 <= float(self.min_fraction) <= 1.0:
            raise ValueError("min_fraction must be between 0 and 1 inclusive")

    def describe(self) -> Mapping[str, Any]:
        """Return a JSON-serialisable snapshot for cache key derivation."""

        if isinstance(self.aggregator, str):
            aggregator = self.aggregator
        else:
            aggregator = getattr(self.aggregator, "__name__", repr(self.aggregator))

        if isinstance(self.fill_method, str) or self.fill_method is None:
            fill_method: str | None = self.fill_method
        else:
            fill_method = getattr(self.fill_method, "__name__", repr(self.fill_method))

        return {
            "aggregator": aggregator,
            "fill_method": fill_method,
            "fill_limit": self.fill_limit,
            "min_fraction": float(self.min_fraction),
        }


@dataclass(slots=True)
class FractalResampler:
    """Energy-aware hierarchical resampling cache with configurable behaviour."""

    series: pd.Series
    config: FractalResamplerConfig = field(default_factory=FractalResamplerConfig)
    _cache: MutableMapping[TimeFrame, pd.Series] = field(default_factory=dict, init=False)
    _cache_hits: int = field(default=0, init=False)
    _direct_resamples: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.series.index, pd.DatetimeIndex):
            raise TypeError("FractalResampler requires a DatetimeIndex")
        # Normalise ordering once; downstream resampling works on monotonic data.
        self.series = self.series.sort_index()

    def prefill(self, timeframes: Sequence[TimeFrame]) -> None:
        """Warm the cache by resampling a collection of horizons."""

        ordered = sorted(set(timeframes), key=lambda tf: tf.seconds)
        for timeframe in ordered:
            self.resample(timeframe)

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

        resampler = base.resample(timeframe.pandas_freq)
        resampled = self._aggregate(resampler)

        if resampled.empty:
            self._cache[timeframe] = resampled
            return resampled

        coverage = float(resampled.notna().sum()) / float(resampled.size)
        if coverage < self.config.min_fraction:
            raise ValueError("resampled coverage below configured min_fraction")

        resampled = self._fill(resampled)

        self._cache[timeframe] = resampled
        return resampled

    def stats(self) -> Mapping[str, float]:
        """Expose cache utilisation metrics for energy profiling."""

        requests = self._cache_hits + self._direct_resamples
        reuse_ratio = (self._cache_hits / requests) if requests else 0.0
        return {
            "resample_requests": float(requests),
            "fractal_cache_hits": float(self._cache_hits),
            "direct_resamples": float(self._direct_resamples),
            "fractal_reuse_ratio": float(reuse_ratio),
            "cache_size": float(len(self._cache)),
        }

    def _aggregate(self, resampler: pd.core.resample.Resampler) -> pd.Series:
        aggregator = self.config.aggregator
        if isinstance(aggregator, str):
            try:
                if hasattr(resampler, aggregator):
                    method = getattr(resampler, aggregator)
                    result = method()
                else:
                    result = resampler.aggregate(aggregator)
            except Exception as exc:  # pragma: no cover - pandas dispatch edge cases
                raise ValueError(f"failed to aggregate using '{aggregator}'") from exc
        else:
            result = resampler.apply(aggregator)

        if isinstance(result, pd.DataFrame):
            if result.shape[1] == 1:
                result = result.iloc[:, 0]
            else:
                raise TypeError(
                    "aggregator returned a DataFrame; provide a reducer that yields a Series"
                )
        if not isinstance(result, pd.Series):
            raise TypeError("aggregator must produce a pandas Series output")
        return result

    def _fill(self, series: pd.Series) -> pd.Series:
        fill_method = self.config.fill_method
        if fill_method is None:
            return series.dropna()
        if isinstance(fill_method, str):
            if fill_method == "ffill":
                filled = series.ffill(limit=self.config.fill_limit)
            elif fill_method == "bfill":
                filled = series.bfill(limit=self.config.fill_limit)
            else:  # pragma: no cover - defensive guard for future literals
                raise ValueError(f"unsupported fill method: {fill_method}")
        else:
            filled = fill_method(series.copy())
            if not isinstance(filled, pd.Series):
                raise TypeError("fill callable must return a pandas Series")
        return filled.dropna()

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
    """

    x = np.asarray(series, dtype=float)
    if x.size == 0:
        raise ValueError("phase extraction requires at least one sample")
    if not np.all(np.isfinite(x)):
        finite = x[np.isfinite(x)]
        if finite.size == 0:
            x = np.zeros_like(x)
        else:
            fill_value = float(np.mean(finite))
            x = np.where(np.isfinite(x), x, fill_value)
    if _signal is None:
        # fallback: leverage FFT-based analytic signal
        n = x.size
        if n > 1:
            idx = np.arange(n, dtype=float)
            coeffs = np.polyfit(idx, x, deg=1)
            trend = np.polyval(coeffs, idx)
            detrended = x - trend
        else:
            detrended = x - float(x.mean())
        X = np.fft.fft(detrended)
        h = np.zeros(n)
        if n % 2 == 0:
            h[0] = h[n // 2] = 1
            h[1 : n // 2] = 2
        else:
            h[0] = 1
            h[1 : (n + 1) // 2] = 2
        analytic = np.fft.ifft(X * h)
    else:
        detrended = _signal.detrend(x)
        analytic = _signal.hilbert(detrended)
    return np.angle(analytic)


def _kuramoto(phases: np.ndarray) -> tuple[float, float]:
    """Compute Kuramoto order parameter and mean phase."""

    complex_mean = np.mean(np.exp(1j * phases))
    return float(np.abs(complex_mean)), float(np.angle(complex_mean))


class WaveletWindowSelector:
    """Selects an analysis window via wavelet energy concentration."""

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

    def select_window(self, prices: Sequence[float]) -> int:
        if self.max_window > 1_048_576:
            raise ValueError(
                "max_window is excessively large for efficient wavelet analysis"
            )
        if self.levels > 8192:
            raise ValueError(
                "levels is excessively large and could exhaust memory during wavelet selection"
            )
        values = np.asarray(prices, dtype=float)
        if values.size == 0:
            raise ValueError("cannot select window from empty price series")
        if self.max_samples is not None and values.size > self.max_samples:
            values = values[-self.max_samples :]
        if _signal is None:
            # geometric mean ensures deterministic, scale-sensitive fallback
            return int(np.sqrt(self.min_window * self.max_window))

        widths = np.linspace(self.min_window, self.max_window, self.levels)
        widths = np.clip(widths, self.min_window, self.max_window)
        widths = np.unique(widths.astype(int))
        widths = widths[widths > 0]
        if widths.size == 0:
            return self.min_window

        try:
            transform = _signal.cwt(values, _signal.ricker, widths)
        except Exception:  # pragma: no cover - SciPy edge cases
            return int(np.sqrt(self.min_window * self.max_window))

        energy = np.sum(transform**2, axis=1)
        best_idx = int(np.argmax(energy))
        best_width = widths[best_idx]
        return int(np.clip(best_width, self.min_window, self.max_window))


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
        resampler_config: FractalResamplerConfig | None = None,
        prefill_timeframes: Sequence[TimeFrame] | Literal["auto"] | None = None,
        resampler_cls: type[FractalResampler] = FractalResampler,
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
        self.resampler_config = (
            resampler_config if resampler_config is not None else FractalResamplerConfig()
        )
        self._prefill_spec = prefill_timeframes
        self.resampler_cls = resampler_cls

    # -- exposed for unit tests -------------------------------------------------
    def _kuramoto_order_parameter(self, phases: np.ndarray) -> tuple[float, float]:
        return _kuramoto(np.asarray(phases, dtype=float))

    # ---------------------------------------------------------------------------
    def _prefill_targets(self) -> tuple[TimeFrame, ...]:
        spec = self._prefill_spec
        if spec is None:
            return ()
        if spec == "auto":
            return tuple(sorted(self.timeframes, key=lambda tf: tf.seconds))
        unique: dict[TimeFrame, None] = {tf: None for tf in spec}
        return tuple(unique.keys())

    def _resample_prices(self, series: pd.Series, timeframe: TimeFrame) -> pd.Series:
        helper = self.resampler_cls(series, config=self.resampler_config)
        return helper.resample(timeframe)

    def _window_for_series(self, values: np.ndarray) -> int:
        if self.use_adaptive_window:
            values_list = values.tolist()
            return int(self.selector.select_window(values_list))
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

        resampler = self.resampler_cls(series, config=self.resampler_config)
        prefill_targets = self._prefill_targets()
        if prefill_targets:
            resampler.prefill(prefill_targets)
        timeframe_results: MutableMapping[TimeFrame, KuramotoResult] = {}
        skipped: list[TimeFrame] = []
        windows: list[int] = []
        endpoints: MutableMapping[TimeFrame, pd.Timestamp] = {}
        samples_processed = 0

        analysis_records: dict[TimeFrame, dict[str, Any]] = {}
        ordered = sorted(self.timeframes, key=lambda tf: tf.seconds)
        for timeframe in ordered:
            if timeframe in analysis_records:
                continue
            record: dict[str, Any] = {"result": None, "endpoint": None, "samples": 0}
            try:
                sampled = resampler.resample(timeframe)
            except ValueError:
                record["skipped"] = True
                analysis_records[timeframe] = record
                continue

            if sampled.empty:
                record["skipped"] = True
                analysis_records[timeframe] = record
                continue

            phases = _hilbert_phase(sampled.values)
            window = min(self._window_for_series(sampled.values), phases.size)
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
                    "skipped": False,
                }
            )
            analysis_records[timeframe] = record

        accounted_for_samples: set[TimeFrame] = set()
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
        resampler_config = getattr(self.analyzer, "resampler_config", None)
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
        config_description = (
            resampler_config.describe()
            if resampler_config is not None
            else FractalResamplerConfig().describe()
        )
        params["resampler"] = dict(config_description)
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
            try:
                sampled = self.analyzer._resample_prices(price_series, timeframe)
            except ValueError:
                continue
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


__all__ = [
    "MultiScaleKuramoto",
    "MultiScaleKuramotoFeature",
    "MultiScaleResult",
    "KuramotoResult",
    "TimeFrame",
    "WaveletWindowSelector",
    "FractalResampler",
    "FractalResamplerConfig",
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
