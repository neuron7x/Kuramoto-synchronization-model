"""Post-training and dynamic quantization utilities.

The module provides light-weight utilities to quantize numpy arrays or
model embeddings to lower precision representations such as ``int8`` or
``float16``.  It focuses on transparency by returning rich telemetry that
captures the numerical error introduced by quantization together with the
latency of the operation.  A fallback path keeps precision untouched when
quantization would degrade the signal (for example when the dynamic range
is degenerate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping, MutableMapping

import numpy as np

__all__ = [
    "QuantizationConfig",
    "QuantizationResult",
    "UniformAffineQuantizer",
]


TargetDType = Literal["int8", "float16"]
QuantizationScheme = Literal["post_training", "dynamic"]


@dataclass(slots=True)
class QuantizationConfig:
    """Configuration describing how quantization should be performed."""

    target_dtype: TargetDType = "int8"
    scheme: QuantizationScheme = "post_training"
    symmetric: bool = True
    allow_fallback: bool = True
    eps: float = 1e-12

    def __post_init__(self) -> None:
        if self.target_dtype not in {"int8", "float16"}:
            raise ValueError("target_dtype must be either 'int8' or 'float16'")
        if self.scheme not in {"post_training", "dynamic"}:
            raise ValueError("scheme must be 'post_training' or 'dynamic'")
        if self.eps <= 0:
            raise ValueError("eps must be positive")


@dataclass(slots=True)
class QuantizationResult:
    """Outcome of a quantization run."""

    quantized: np.ndarray
    reconstructed: np.ndarray
    dtype: np.dtype
    method: QuantizationScheme
    scale: float | None
    zero_point: float | None
    calibration_range: tuple[float, float] | None
    latency_ms: float
    fallback_used: bool
    error_metrics: MutableMapping[str, float] = field(default_factory=dict)

    def as_dict(self) -> Mapping[str, float | str | bool]:
        """Serialise the most relevant metrics for logging systems."""

        payload: MutableMapping[str, float | str | bool] = {
            "method": self.method,
            "dtype": str(self.dtype),
            "latency_ms": float(self.latency_ms),
            "fallback_used": bool(self.fallback_used),
        }
        if self.scale is not None:
            payload["scale"] = float(self.scale)
        if self.zero_point is not None:
            payload["zero_point"] = float(self.zero_point)
        if self.calibration_range is not None:
            payload["calib_min"] = float(self.calibration_range[0])
            payload["calib_max"] = float(self.calibration_range[1])
        for key, value in self.error_metrics.items():
            payload[key] = float(value)
        return payload


def _dtype_bounds(dtype: np.dtype) -> tuple[int, int]:
    info = np.iinfo(dtype)
    return int(info.min), int(info.max)


def _combine_arrays(batch: Iterable[np.ndarray]) -> np.ndarray:
    values = [np.asarray(sample, dtype=np.float32).ravel() for sample in batch]
    if not values:
        raise ValueError("calibration data must not be empty")
    return np.concatenate(values)


def _error_metrics(
    reference: np.ndarray, approx: np.ndarray, eps: float
) -> MutableMapping[str, float]:
    ref = np.asarray(reference, dtype=np.float32)
    recon = np.asarray(approx, dtype=np.float32)
    diff = ref - recon
    mse = float(np.mean(diff**2))
    mae = float(np.mean(np.abs(diff)))
    max_abs = float(np.max(np.abs(diff))) if diff.size else 0.0
    signal_power = float(np.sum(ref**2))
    noise_power = float(np.sum(diff**2))
    if noise_power <= eps:
        snr_db = float("inf")
    else:
        snr_db = float(10.0 * np.log10((signal_power + eps) / (noise_power + eps)))
    return {
        "mse": mse,
        "mae": mae,
        "max_abs_err": max_abs,
        "snr_db": snr_db,
    }


class UniformAffineQuantizer:
    """Uniform affine quantizer with optional post-training calibration."""

    def __init__(self, config: QuantizationConfig | None = None) -> None:
        self.config = config or QuantizationConfig()
        self._scale: float | None = None
        self._zero_point: float | None = None
        self._calibration_range: tuple[float, float] | None = None
        self._calibrated = False
        self._int_bounds = _dtype_bounds(np.int8)
        self._target_dtype = np.dtype(
            np.int8 if self.config.target_dtype == "int8" else np.float16
        )

    def calibrate(self, samples: Iterable[np.ndarray] | np.ndarray) -> None:
        """Register calibration samples to estimate the dynamic range."""

        if isinstance(samples, np.ndarray):
            arr = np.asarray(samples, dtype=np.float32).ravel()
        else:
            arr = _combine_arrays(samples)
        if arr.size == 0:
            raise ValueError("calibration samples cannot be empty")
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        if self.config.symmetric:
            bound = max(abs(min_val), abs(max_val))
            min_val, max_val = -bound, bound
        scale, zero_point = self._scale_from_range(min_val, max_val)
        self._scale = scale
        self._zero_point = zero_point
        self._calibration_range = (min_val, max_val)
        self._calibrated = True

    def quantize(self, values: np.ndarray) -> QuantizationResult:
        """Quantize ``values`` according to the configuration.

        The method performs the quantization, reconstructs the signal, and
        reports the induced numerical error as well as the time it took to
        execute.  When quantization is unsafe and ``allow_fallback`` is
        enabled the method falls back to ``float16`` casting.
        """

        import time

        arr = np.asarray(values, dtype=np.float32)
        if arr.ndim == 0:
            arr = arr.reshape(1)

        start = time.perf_counter()
        if self._target_dtype == np.float16:
            quantized = arr.astype(np.float16)
            scale = None
            zero_point = None
            calib_range = None
            dtype = np.dtype(np.float16)
            fallback_used = False
        else:
            scale, zero_point, calib_range = self._resolve_params(arr)
            if scale is None or not np.isfinite(scale) or scale == 0.0:
                if self.config.allow_fallback:
                    quantized = arr.astype(np.float16)
                    dtype = np.dtype(np.float16)
                    scale = None
                    zero_point = None
                    calib_range = None
                    fallback_used = True
                else:
                    raise RuntimeError(
                        "Degenerate scale encountered during quantization"
                    )
            else:
                qmin, qmax = self._int_bounds
                transformed = np.round(arr / scale + zero_point)
                quantized = np.clip(transformed, qmin, qmax).astype(np.int8)
                dtype = np.dtype(np.int8)
                fallback_used = False
        latency_ms = (time.perf_counter() - start) * 1_000.0

        reconstructed = self._dequantize(quantized, scale, zero_point)
        errors = _error_metrics(arr, reconstructed, self.config.eps)
        return QuantizationResult(
            quantized=quantized,
            reconstructed=reconstructed,
            dtype=dtype,
            method=self.config.scheme,
            scale=scale,
            zero_point=zero_point,
            calibration_range=calib_range,
            latency_ms=latency_ms,
            fallback_used=fallback_used,
            error_metrics=errors,
        )

    def _resolve_params(
        self, arr: np.ndarray
    ) -> tuple[float | None, float | None, tuple[float, float] | None]:
        if self.config.scheme == "post_training":
            if not self._calibrated:
                self.calibrate(arr)
            return self._scale, self._zero_point, self._calibration_range
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        if self.config.symmetric:
            bound = max(abs(min_val), abs(max_val))
            min_val, max_val = -bound, bound
        scale, zero_point = self._scale_from_range(min_val, max_val)
        return scale, zero_point, (min_val, max_val)

    def _scale_from_range(
        self, min_val: float, max_val: float
    ) -> tuple[float | None, float | None]:
        if max_val - min_val <= self.config.eps:
            return None, None
        qmin, qmax = self._int_bounds
        scale = (max_val - min_val) / float(qmax - qmin)
        zero_point = qmin - np.round(min_val / scale)
        zero_point = float(np.clip(zero_point, qmin, qmax))
        return float(scale), float(zero_point)

    @staticmethod
    def _dequantize(
        quantized: np.ndarray, scale: float | None, zero_point: float | None
    ) -> np.ndarray:
        if quantized.dtype == np.int8:
            if scale is None or zero_point is None:
                raise RuntimeError("Missing scale/zero_point for int8 dequantization")
            return (quantized.astype(np.float32) - float(zero_point)) * float(scale)
        if quantized.dtype == np.float16:
            return quantized.astype(np.float32)
        return quantized.astype(np.float32)
