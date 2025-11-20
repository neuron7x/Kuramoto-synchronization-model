from __future__ import annotations

import numpy as np

from core.ml.quantization import QuantizationConfig, UniformAffineQuantizer


def test_post_training_int8_quantization_high_fidelity() -> None:
    rng = np.random.default_rng(7)
    calibration = rng.normal(0.0, 1.0, size=2_048)
    batch = rng.normal(0.0, 1.0, size=512)

    quantizer = UniformAffineQuantizer(
        QuantizationConfig(target_dtype="int8", scheme="post_training", symmetric=True)
    )
    quantizer.calibrate(calibration)
    result = quantizer.quantize(batch)

    assert result.quantized.dtype == np.int8
    assert not result.fallback_used
    assert result.scale is not None and result.zero_point is not None
    assert result.error_metrics["mse"] < 1e-2
    assert result.error_metrics["snr_db"] > 20.0


def test_dynamic_quantization_without_calibration() -> None:
    values = np.linspace(-1.5, 1.5, num=33, dtype=np.float32)
    quantizer = UniformAffineQuantizer(
        QuantizationConfig(target_dtype="int8", scheme="dynamic")
    )

    result = quantizer.quantize(values)

    assert result.quantized.dtype == np.int8
    assert result.calibration_range is not None
    assert result.error_metrics["max_abs_err"] <= 0.2
    np.testing.assert_allclose(result.reconstructed, values, atol=0.15)


def test_quantization_fallback_to_float16_when_range_degenerate() -> None:
    quantizer = UniformAffineQuantizer(
        QuantizationConfig(target_dtype="int8", allow_fallback=True, symmetric=False)
    )
    calibration = np.ones(32, dtype=np.float32)
    quantizer.calibrate(calibration)

    data = np.ones(16, dtype=np.float32)
    result = quantizer.quantize(data)

    assert result.fallback_used is True
    assert result.quantized.dtype == np.float16
    assert result.scale is None and result.zero_point is None
    np.testing.assert_array_equal(result.reconstructed, data.astype(np.float32))
    assert result.error_metrics["mse"] == 0.0
