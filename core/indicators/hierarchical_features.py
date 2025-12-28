"""Hierarchical feature computation for multi-timeframe analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, MutableMapping, Optional, Sequence

import numpy as np
import pandas as pd

from core.data.resampling import _ensure_datetime_index

from .hurst import hurst_exponent
from .kuramoto import compute_phase


@dataclass(frozen=True)
class TimeFrameSpec:
    """Descriptor for each timeframe used in the hierarchy."""

    name: str
    frequency: str


@dataclass
class FeatureBufferCache:
    """Cache float32 buffers to avoid repeated allocations."""

    store: MutableMapping[str, np.ndarray] = field(default_factory=dict)

    def array(self, key: str, values: Sequence[float]) -> np.ndarray:
        src = np.asarray(values, dtype=np.float32)
        existing = self.store.get(key)
        if existing is None or existing.shape != src.shape:
            existing = np.empty_like(src)
            self.store[key] = existing
        np.copyto(existing, src, casting="unsafe")
        return existing

    def buffer(
        self,
        key: str,
        shape: tuple[int, ...],
        *,
        dtype: np.dtype | type = np.float32,
    ) -> np.ndarray:
        arr = self.store.get(key)
        if arr is None or arr.shape != shape or arr.dtype != np.dtype(dtype):
            arr = np.empty(shape, dtype=dtype)
            self.store[key] = arr
        return arr


_ENTROPY_BIN_COUNT = 30
_ENTROPY_SCALE = np.float32(_ENTROPY_BIN_COUNT / 2.0)
_ENTROPY_CLIP = np.nextafter(np.float32(_ENTROPY_BIN_COUNT), np.float32(0.0))


def _shannon_entropy(series: np.ndarray, bins: int = _ENTROPY_BIN_COUNT) -> float:
    values = np.asarray(series, dtype=np.float32)
    if values.size == 0:
        return 0.0

    mask = np.isfinite(values)
    if not np.any(mask):
        return 0.0

    finite = values[mask].astype(np.float32)
    max_abs = float(np.max(np.abs(finite)))
    if not max_abs or not np.isfinite(max_abs):
        return 0.0

    np.divide(finite, max_abs, out=finite)
    np.clip(finite, -1.0, 1.0, out=finite)

    scale = _ENTROPY_SCALE if bins == _ENTROPY_BIN_COUNT else np.float32(bins / 2.0)
    clip = (
        _ENTROPY_CLIP
        if bins == _ENTROPY_BIN_COUNT
        else np.nextafter(np.float32(bins), np.float32(0.0))
    )
    scaled = (finite + 1.0) * scale
    np.clip(scaled, 0.0, clip, out=scaled)

    indices = scaled.astype(np.int32)
    counts = np.bincount(indices, minlength=bins).astype(np.float32)
    total = float(np.add.reduce(counts, dtype=np.float32))
    if total <= 0.0:
        return 0.0

    np.divide(counts, total, out=counts)
    positive = counts > 0.0
    if not np.any(positive):
        return 0.0

    log_probs = np.empty_like(counts)
    np.log(counts, out=log_probs, where=positive)
    log_probs[~positive] = 0.0
    np.multiply(counts, log_probs, out=log_probs)
    entropy = -float(np.add.reduce(log_probs, dtype=np.float32))
    return entropy


@dataclass
class HierarchicalFeatureResult:
    """Structured container for hierarchical feature outputs."""

    features: Dict[str, Dict[str, float]]
    multi_tf_phase_coherence: float
    benchmarks: Dict[str, float]


def _flatten(features: Mapping[str, Mapping[str, float]]) -> Dict[str, float]:
    return {
        f"{tf}.{name}": value
        for tf, values in features.items()
        for name, value in values.items()
    }


def compute_hierarchical_features(
    ohlcv_by_tf: Mapping[str, pd.DataFrame],
    *,
    book_by_tf: Optional[Mapping[str, pd.DataFrame]] = None,
    benchmarks: Optional[Mapping[str, float]] = None,
    cache: Optional[FeatureBufferCache] = None,
) -> HierarchicalFeatureResult:
    """Compute Kuramoto, entropy, Hurst, book imbalance and microprice metrics."""

    if not ohlcv_by_tf:
        raise ValueError("ohlcv_by_tf must not be empty")
    cache = cache or FeatureBufferCache()
    reference = next(iter(ohlcv_by_tf))
    prepared = {
        name: _ensure_datetime_index(frame) for name, frame in ohlcv_by_tf.items()
    }
    max_samples = max(frame.index.size for frame in prepared.values())
    ref_frame = prepared[reference]
    ref_index = ref_frame.index.asi8
    sample_count = ref_index.size
    if sample_count == 0:
        raise ValueError("reference timeframe must contain data")
    features: Dict[str, Dict[str, float]] = {}
    returns_buffer = cache.buffer(
        "shared:returns_source", (max_samples,), dtype=np.float32
    )
    phase_buffer = cache.buffer("shared:phase_source", (max_samples,), dtype=np.float32)
    cos_buffer = cache.buffer("shared:phase_cos", (max_samples,), dtype=np.float32)
    sin_buffer = cache.buffer("shared:phase_sin", (max_samples,), dtype=np.float32)
    finite_mask = cache.buffer("shared:phase_finite", (max_samples,), dtype=bool)
    hurst_scratch_buffer = cache.buffer(
        "shared:hurst_diff", (max_samples,), dtype=np.float32
    )
    hurst_tau_buffer = cache.buffer(
        "shared:hurst_tau", (_DEFAULT_LAGS.size,), dtype=np.float32
    )
    agg_cos = cache.buffer("phase_accum_cos", (sample_count,))
    agg_sin = cache.buffer("phase_accum_sin", (sample_count,))
    agg_counts = cache.buffer("phase_accum_counts", (sample_count,), dtype=np.int32)
    agg_cos.fill(0.0)
    agg_sin.fill(0.0)
    agg_counts.fill(0)
    for name, frame in prepared.items():
        close_src = frame["close"].to_numpy(dtype=np.float32, copy=False)
        if close_src.size == 0:
            features[name] = {"entropy": 0.0, "hurst": 0.5, "kuramoto": 0.0}
            continue

        returns_source = returns_buffer[: close_src.size]
        returns_source.fill(0.0)
        if close_src.size > 1:
            np.subtract(close_src[1:], close_src[:-1], out=returns_source[1:])

        phase_source = compute_phase(
            returns_source,
            use_float32=True,
            out=phase_buffer[: close_src.size],
        )
        finite_source = np.isfinite(phase_source, out=finite_mask[: close_src.size])

        cos_view = cos_buffer[: close_src.size]
        sin_view = sin_buffer[: close_src.size]
        cos_view.fill(0.0)
        sin_view.fill(0.0)
        np.cos(phase_source, out=cos_view, where=finite_source)
        np.sin(phase_source, out=sin_view, where=finite_source)

        finite_count = int(finite_source.sum(dtype=np.int32))
        if finite_count:
            cos_valid = cos_view[finite_source]
            sin_valid = sin_view[finite_source]
            local_sum_real = float(np.add.reduce(cos_valid, dtype=np.float64))
            local_sum_imag = float(np.add.reduce(sin_valid, dtype=np.float64))
            local_magnitude = (
                local_sum_real * local_sum_real + local_sum_imag * local_sum_imag
            ) ** 0.5
            local_kuramoto = float(np.clip(local_magnitude / finite_count, 0.0, 1.0))
        else:
            local_kuramoto = 0.0

        idx = frame.index.asi8
        if idx.size:
            positions = np.searchsorted(idx, ref_index, side="right") - 1
            valid_mask = positions >= 0
            if np.any(valid_mask):
                ref_positions = np.nonzero(valid_mask)[0]
                src_positions = positions[valid_mask]
                finite_aligned = finite_source[src_positions]
                if np.any(finite_aligned):
                    aligned_indices = src_positions[finite_aligned]
                    bins = ref_positions[finite_aligned]
                    cos_aligned = cos_view[aligned_indices]
                    sin_aligned = sin_view[aligned_indices]
                    unique_bins, first_idx, counts = np.unique(
                        bins, return_index=True, return_counts=True
                    )
                    cos_sums = np.add.reduceat(cos_aligned, first_idx).astype(
                        np.float32, copy=False
                    )
                    sin_sums = np.add.reduceat(sin_aligned, first_idx).astype(
                        np.float32, copy=False
                    )
                    agg_cos[unique_bins] += cos_sums
                    agg_sin[unique_bins] += sin_sums
                    agg_counts[unique_bins] += counts.astype(np.int32)

        hurst_scratch = hurst_scratch_buffer[: close_src.size]
        hurst_tau = hurst_tau_buffer[: _DEFAULT_LAGS.size]
        features[name] = {
            "entropy": _shannon_entropy(returns_source),
            "hurst": float(
                hurst_exponent(
                    close_src,
                    use_float32=True,
                    scratch=hurst_scratch,
                    tau_buffer=hurst_tau,
                )
            ),
            "kuramoto": local_kuramoto,
        }
        if book_by_tf and name in book_by_tf:
            book = book_by_tf[name]
            imbalance = book.get("imbalance")
            microprice = book.get("microprice")
            if imbalance is not None:
                features[name]["book_imbalance"] = float(
                    np.nanmean(np.asarray(imbalance, dtype=np.float32))
                )
            if microprice is not None:
                micro = np.asarray(microprice, dtype=np.float32)
                length = min(micro.size, close_src.size)
                if length:
                    price_delta = micro[:length] - close_src[:length]
                    features[name]["microprice_basis"] = float(np.nanmean(price_delta))
    valid = agg_counts > 0
    if not np.any(valid):
        phase_coherence = 0.0
    else:
        magnitude = np.hypot(
            agg_cos.astype(np.float64),
            agg_sin.astype(np.float64),
        )
        counts = agg_counts.astype(np.float64)
        coherence = np.divide(
            magnitude,
            counts,
            out=np.zeros_like(magnitude, dtype=np.float64),
            where=valid,
        )
        coherence[~valid] = np.nan
        phase_coherence = float(np.nanmean(coherence))
    benchmark_diff: Dict[str, float] = {}
    if benchmarks:
        flat = _flatten(features)
        for key, expected in benchmarks.items():
            actual = flat.get(key)
            if actual is not None:
                benchmark_diff[key] = float(actual - expected)
    return HierarchicalFeatureResult(
        features=features,
        multi_tf_phase_coherence=phase_coherence,
        benchmarks=benchmark_diff,
    )


__all__ = [
    "FeatureBufferCache",
    "HierarchicalFeatureResult",
    "TimeFrameSpec",
    "compute_hierarchical_features",
]

_DEFAULT_LAGS = np.arange(2, 51, dtype=int)
