# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T2b: Stuart-Landau ES proximity as an early-warning substrate.

This module mirrors the T2 Kuramoto explosive-synchronization detector but keeps
amplitude dynamics:

    dz_i/dt = (mu_i + i*omega_i) z_i - |z_i|^2 z_i
              + (K/N) sum_j (z_j - z_i)

The empirical real-data lead claim is not promoted here. The live runtime
contract is narrower: amplitude is non-negative, ES proximity is bounded, the
fitted sweep starts from observed analytic state by default, mu clipping is
visible, and evidence paths can fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, TypeAlias

import numpy as np
from numpy.typing import NDArray

_DEFAULT_K_LOW: Final[float] = 0.0
_DEFAULT_K_HIGH: Final[float] = 4.0
_DEFAULT_K_STEPS: Final[int] = 16
_DEFAULT_INT_STEPS: Final[int] = 200
_DEFAULT_DT: Final[float] = 0.05
# bounds: amplitude is |analytic signal| and must never be negative.
_AMPLITUDE_FLOOR: Final[float] = 0.0
# bounds: Euler-stable growth-rate band; mu=0 remains the Hopf threshold.
_MU_GROWTH_CLAMP: Final[float] = 1.0

__all__ = [
    "StuartLandauResult",
    "fit_stuart_landau",
    "rolling_es_proximity",
    "crisis_signal_sl",
]


FloatArray: TypeAlias = NDArray[np.float64]
BoolArray: TypeAlias = NDArray[np.bool_]
ComplexArray: TypeAlias = NDArray[np.complex128]


def _analytic_signal(values: FloatArray, axis: int = 0) -> ComplexArray:
    """Return a NumPy-only analytic signal along ``axis``.

    This mirrors the FFT-domain Hilbert transform used only to obtain an
    amplitude envelope and phase. Keeping it local removes a hidden SciPy
    dependency from the mutation gate's minimal physics runtime.
    """
    arr = np.asarray(values, dtype=np.float64)
    n = arr.shape[axis]
    spectrum = np.fft.fft(arr, axis=axis)
    freq = np.fft.fftfreq(n)
    multiplier = (1.0 + np.sign(freq)).astype(np.float64)
    multiplier[np.isclose(freq, 0.0)] = 1.0
    multiplier[np.isclose(np.abs(freq), 0.5)] = 1.0
    shape = [1] * arr.ndim
    shape[axis] = n
    analytic = np.fft.ifft(spectrum * multiplier.reshape(shape), axis=axis)
    return analytic.astype(np.complex128, copy=False)


@dataclass(frozen=True, slots=True)
class StuartLandauResult:
    """Snapshot result of a Stuart-Landau fit and ES proximity sweep."""

    amplitude: FloatArray
    phase: FloatArray
    order_parameter: float
    hysteresis_area: float
    es_proximity: float
    leads_r_peak: bool
    mu_raw: FloatArray
    mu_clamped: FloatArray
    mu_was_clipped: BoolArray
    mu_clip_count: int
    mu_clip_mass: float

    def __post_init__(self) -> None:
        if np.any(self.amplitude < _AMPLITUDE_FLOOR):
            raise ValueError(
                "INV-SL1 VIOLATED: amplitude below floor in fitted "
                f"Stuart-Landau ensemble. min={float(self.amplitude.min()):.6e}."
            )
        if not (0.0 <= self.es_proximity <= 1.0):
            raise ValueError(
                "INV-SL2 VIOLATED: es_proximity outside [0, 1]. "
                f"value={self.es_proximity:.6e}, "
                f"area={self.hysteresis_area:.6e}."
            )
        if self.mu_raw.shape != self.mu_clamped.shape:
            raise ValueError(
                "INV-SL mu audit VIOLATED: raw/clamped shape mismatch. "
                f"raw={self.mu_raw.shape}, clamped={self.mu_clamped.shape}."
            )
        if self.mu_was_clipped.shape != self.mu_raw.shape:
            raise ValueError(
                "INV-SL mu audit VIOLATED: clipped mask shape mismatch. "
                f"mask={self.mu_was_clipped.shape}, raw={self.mu_raw.shape}."
            )
        expected_count = int(np.count_nonzero(self.mu_was_clipped))
        if self.mu_clip_count != expected_count:
            raise ValueError(
                "INV-SL mu audit VIOLATED: clip count does not match mask. "
                f"count={self.mu_clip_count}, expected={expected_count}."
            )
        if self.mu_clip_mass < 0.0 or not np.isfinite(self.mu_clip_mass):
            raise ValueError(
                "INV-SL mu audit VIOLATED: clip mass must be finite and "
                f"non-negative, got {self.mu_clip_mass!r}."
            )


def _validate_prices(prices: FloatArray, min_T: int = 8) -> None:
    """Validate the common price-panel contract."""
    if prices.ndim != 2:
        raise ValueError(
            "INV-SL contract VIOLATED: prices shape (T, N) required, "
            f"got ndim={prices.ndim}, shape={prices.shape}."
        )
    if prices.shape[0] < min_T:
        raise ValueError(
            f"INV-SL contract VIOLATED: T>={min_T} required, "
            f"got T={prices.shape[0]}, N={prices.shape[1]}."
        )
    if prices.shape[1] < 2:
        raise ValueError(
            "INV-SL contract VIOLATED: N>=2 oscillators required, "
            f"got N={prices.shape[1]}, T={prices.shape[0]}."
        )
    if not np.all(np.isfinite(prices)):
        raise ValueError("INV-SL contract VIOLATED: prices must be finite.")
    if np.any(prices <= 0.0):
        raise ValueError("INV-SL contract VIOLATED: prices must be strictly positive.")


def _validate_sweep_config(
    *,
    K_low: float,
    K_high: float,
    K_steps: int,
    int_steps: int,
    dt: float,
    source: str,
) -> None:
    """Validate sweep and integration parameters before simulation."""
    if not np.isfinite(K_low) or not np.isfinite(K_high):
        raise ValueError(
            "INV-SL contract VIOLATED: finite K_low/K_high required, "
            f"got K_low={K_low}, K_high={K_high}. Source: {source}."
        )
    if K_low >= K_high:
        raise ValueError(
            "INV-SL contract VIOLATED: K_low<K_high required, "
            f"got K_low={K_low}, K_high={K_high}. Source: {source}."
        )
    if not isinstance(K_steps, int) or K_steps < 2:
        raise ValueError(
            "INV-SL contract VIOLATED: integer K_steps>=2 required, "
            f"got {K_steps!r}. Source: {source}."
        )
    if not isinstance(int_steps, int) or int_steps < 1:
        raise ValueError(
            "INV-SL contract VIOLATED: integer int_steps>=1 required, "
            f"got {int_steps!r}. Source: {source}."
        )
    if not np.isfinite(dt) or dt <= 0.0:
        raise ValueError(
            f"INV-SL contract VIOLATED: finite dt>0 required, got {dt}. Source: {source}."
        )


def _estimate_growth_rate_audit(
    amplitude_envelope: FloatArray,
) -> tuple[FloatArray, FloatArray, BoolArray, int, float]:
    """Return raw mu, clamped mu, clipped mask/count/mass."""
    n_t = amplitude_envelope.shape[0]
    t = np.arange(n_t, dtype=np.float64)
    t_centred = t - t.mean()
    t_var = float((t_centred * t_centred).sum())
    if t_var <= 0.0:
        raise ValueError(
            "INV-SL contract VIOLATED: growth-rate regression needs "
            f"nonzero time variance, got n_t={n_t}."
        )

    # bounds: log floor prevents log(0) without hiding the raw fitted mu.
    log_amp = np.log(np.maximum(amplitude_envelope, 1e-12))
    log_amp_centred = log_amp - log_amp.mean(axis=0)
    mu_raw = (t_centred[:, None] * log_amp_centred).sum(axis=0) / t_var
    mu_raw = mu_raw.astype(np.float64)
    # bounds: clamp only caps explicit-Euler blow-up; raw mu is retained.
    mu_clamped = np.clip(
        mu_raw,
        -_MU_GROWTH_CLAMP,
        _MU_GROWTH_CLAMP,
    ).astype(np.float64)
    mu_was_clipped = np.not_equal(mu_raw, mu_clamped).astype(np.bool_)
    mu_clip_count = int(np.count_nonzero(mu_was_clipped))
    mu_clip_mass = float(np.abs(mu_raw - mu_clamped).sum())
    return mu_raw, mu_clamped, mu_was_clipped, mu_clip_count, mu_clip_mass


def _estimate_growth_rate(amplitude_envelope: FloatArray) -> FloatArray:
    """Estimate clamped Stuart-Landau linear growth rate mu."""
    _, mu_clamped, _, _, _ = _estimate_growth_rate_audit(amplitude_envelope)
    return mu_clamped


def _extract_amplitude_phase_omega_mu_audit(
    prices: FloatArray,
) -> tuple[
    FloatArray,
    FloatArray,
    FloatArray,
    FloatArray,
    FloatArray,
    BoolArray,
    int,
    float,
]:
    """Convert a price panel into fitted state plus mu audit surface."""
    log_returns = np.diff(np.log(prices), axis=0)
    centred = log_returns - log_returns.mean(axis=0)
    analytic = _analytic_signal(centred, axis=0)
    amplitude_envelope = np.abs(analytic).astype(np.float64)
    amplitude_last = amplitude_envelope[-1, :]
    phase_last = np.angle(analytic[-1, :]).astype(np.float64)
    phase_unwrapped = np.unwrap(np.angle(analytic), axis=0)
    omega = np.diff(phase_unwrapped, axis=0).mean(axis=0).astype(np.float64)
    (
        mu_raw,
        mu_clamped,
        mu_was_clipped,
        mu_clip_count,
        mu_clip_mass,
    ) = _estimate_growth_rate_audit(amplitude_envelope)
    return (
        amplitude_last,
        phase_last,
        omega,
        mu_raw,
        mu_clamped,
        mu_was_clipped,
        mu_clip_count,
        mu_clip_mass,
    )


def _extract_amplitude_phase_omega(
    prices: FloatArray,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Return amplitude, phase, omega, and clamped mu."""
    extracted = _extract_amplitude_phase_omega_mu_audit(prices)
    amplitude, phase, omega, _, mu_clamped, _, _, _ = extracted
    return amplitude, phase, omega, mu_clamped


def _stuart_landau_step(
    z: ComplexArray,
    mu: FloatArray,
    omega: FloatArray,
    K: float,
    dt: float,
) -> ComplexArray:
    """Single explicit Euler step of the Stuart-Landau ensemble RHS."""
    n = z.shape[0]
    coupling = (K / n) * (z.sum() - n * z)
    self_term = (mu + 1j * omega) * z - (np.abs(z) ** 2) * z
    out: ComplexArray = (z + dt * (self_term + coupling)).astype(
        np.complex128,
        copy=False,
    )
    return out


def _r_at_K(
    mu: FloatArray,
    omega: FloatArray,
    K: float,
    z0: ComplexArray,
    steps: int,
    dt: float,
) -> tuple[float, ComplexArray]:
    """Integrate ensemble at fixed K and return final R and state."""
    z = z0.copy()
    for _ in range(steps):
        z = _stuart_landau_step(z, mu, omega, K, dt)
    order = np.mean(np.exp(1j * np.angle(z)))
    return float(np.abs(order)), z


def _initial_state_from_seed(n: int, seed: int) -> ComplexArray:
    """Explicit fallback state for synthetic/random-init probes only."""
    rng = np.random.default_rng(seed)
    z = np.empty(n, dtype=np.complex128)
    z.real = rng.standard_normal(n) * 0.1
    z.imag = rng.standard_normal(n) * 0.1
    return z


def _validate_z0(z0: ComplexArray, n: int) -> ComplexArray:
    """Validate and copy an externally supplied fitted complex state."""
    if z0.shape != (n,):
        raise ValueError(f"INV-SL contract VIOLATED: z0 shape {(n,)} required, got {z0.shape}.")
    if not np.all(np.isfinite(z0.real)) or not np.all(np.isfinite(z0.imag)):
        raise ValueError("INV-SL contract VIOLATED: z0 must be finite.")
    return z0.astype(np.complex128, copy=True)


def _hysteresis_sweep(
    mu: FloatArray,
    omega: FloatArray,
    *,
    K_low: float,
    K_high: float,
    K_steps: int,
    int_steps: int,
    dt: float,
    seed: int,
    z0: ComplexArray | None = None,
) -> tuple[float, FloatArray, FloatArray]:
    """Forward/backward K-sweep with fitted-state default."""
    _validate_sweep_config(
        K_low=K_low,
        K_high=K_high,
        K_steps=K_steps,
        int_steps=int_steps,
        dt=dt,
        source="stuart_landau_es._hysteresis_sweep",
    )
    n = mu.shape[0]
    if z0 is None:
        z = _initial_state_from_seed(n, seed)
    else:
        z = _validate_z0(z0, n)

    K_grid = np.linspace(K_low, K_high, K_steps)
    R_fwd = np.zeros(K_steps, dtype=np.float64)
    for index, K in enumerate(K_grid):
        R_fwd[index], z = _r_at_K(mu, omega, float(K), z, int_steps, dt)

    R_bwd = np.zeros(K_steps, dtype=np.float64)
    for index, K in enumerate(K_grid[::-1]):
        out_index = K_steps - 1 - index
        R_bwd[out_index], z = _r_at_K(mu, omega, float(K), z, int_steps, dt)

    # bounds: avoid zero-width K normalization while preserving a zero area.
    K_range = max(K_high - K_low, 1e-12)
    area = float(np.trapezoid(np.abs(R_fwd - R_bwd), K_grid)) / K_range
    return area, R_fwd, R_bwd


def fit_stuart_landau(
    prices: FloatArray,
    *,
    K_low: float = _DEFAULT_K_LOW,
    K_high: float = _DEFAULT_K_HIGH,
    K_steps: int = _DEFAULT_K_STEPS,
    int_steps: int = _DEFAULT_INT_STEPS,
    dt: float = _DEFAULT_DT,
    seed: int = 42,
) -> StuartLandauResult:
    """Fit a Stuart-Landau ensemble to a price panel."""
    _validate_prices(prices, min_T=8)
    _validate_sweep_config(
        K_low=K_low,
        K_high=K_high,
        K_steps=K_steps,
        int_steps=int_steps,
        dt=dt,
        source="stuart_landau_es.fit_stuart_landau",
    )

    (
        amplitude,
        phase,
        omega,
        mu_raw,
        mu_clamped,
        mu_was_clipped,
        mu_clip_count,
        mu_clip_mass,
    ) = _extract_amplitude_phase_omega_mu_audit(prices)
    order_parameter = float(np.abs(np.mean(np.exp(1j * phase))))
    fitted_z0 = (amplitude * np.exp(1j * phase)).astype(np.complex128)
    area, _, _ = _hysteresis_sweep(
        mu_clamped,
        omega,
        K_low=K_low,
        K_high=K_high,
        K_steps=K_steps,
        int_steps=int_steps,
        dt=dt,
        seed=seed,
        z0=fitted_z0,
    )
    # bounds: public ES proximity is a [0, 1] scalar; raw area is retained.
    es_proximity = float(np.clip(area, 0.0, 1.0))

    return StuartLandauResult(
        amplitude=np.abs(amplitude),
        phase=phase,
        order_parameter=order_parameter,
        hysteresis_area=area,
        es_proximity=es_proximity,
        leads_r_peak=False,
        mu_raw=mu_raw,
        mu_clamped=mu_clamped,
        mu_was_clipped=mu_was_clipped,
        mu_clip_count=mu_clip_count,
        mu_clip_mass=mu_clip_mass,
    )


def rolling_es_proximity(
    prices: FloatArray,
    window: int,
    *,
    step: int = 1,
    K_low: float = _DEFAULT_K_LOW,
    K_high: float = _DEFAULT_K_HIGH,
    K_steps: int = _DEFAULT_K_STEPS,
    int_steps: int = _DEFAULT_INT_STEPS,
    dt: float = _DEFAULT_DT,
    seed: int = 42,
    fail_closed: bool = False,
) -> FloatArray:
    """Causal rolling ES proximity series, one fit per window endpoint."""
    _validate_prices(prices, min_T=window)
    if window < 8:
        raise ValueError(f"INV-SL contract VIOLATED: window>=8, got {window}.")
    if step < 1:
        raise ValueError(f"INV-SL contract VIOLATED: step>=1, got {step}.")

    T = prices.shape[0]
    out = np.full(T, np.nan, dtype=np.float64)
    for window_end in range(window - 1, T, step):
        slab = prices[window_end - window + 1 : window_end + 1]
        try:
            res = fit_stuart_landau(
                slab,
                K_low=K_low,
                K_high=K_high,
                K_steps=K_steps,
                int_steps=int_steps,
                dt=dt,
                seed=seed,
            )
            out[window_end] = res.es_proximity
        except (ValueError, FloatingPointError) as exc:
            if fail_closed:
                raise RuntimeError(
                    "INV-SL rolling fail-closed: "
                    f"window_end={window_end}, window={window}, cause={exc}"
                ) from exc
            out[window_end] = np.nan
    return out


def crisis_signal_sl(
    prices: FloatArray,
    *,
    es_threshold: float = 0.3,
    K_low: float = _DEFAULT_K_LOW,
    K_high: float = _DEFAULT_K_HIGH,
    K_steps: int = _DEFAULT_K_STEPS,
    int_steps: int = _DEFAULT_INT_STEPS,
    dt: float = _DEFAULT_DT,
    seed: int = 42,
) -> dict[str, float | bool]:
    """Single-shot Stuart-Landau crisis signal.

    Issue #1358 P1-3: the mu-clip audit is surfaced here (``mu_clip_count``,
    ``mu_clip_mass``, ``mu_was_clipped_any``) so a downstream consumer using this
    compact signal as evidence can still see whether the growth-rate estimate was
    clamped — a clipped window is not silently indistinguishable from a clean one.
    """
    res = fit_stuart_landau(
        prices,
        K_low=K_low,
        K_high=K_high,
        K_steps=K_steps,
        int_steps=int_steps,
        dt=dt,
        seed=seed,
    )
    return {
        "es_proximity": res.es_proximity,
        "hysteresis_area": res.hysteresis_area,
        "order_parameter": res.order_parameter,
        "amplitude_max": float(res.amplitude.max()),
        "amplitude_min": float(res.amplitude.min()),
        "is_explosive": bool(res.es_proximity > es_threshold),
        "leads_r_peak": res.leads_r_peak,
        "mu_clip_count": res.mu_clip_count,
        "mu_clip_mass": res.mu_clip_mass,
        "mu_was_clipped_any": bool(np.any(res.mu_was_clipped)),
    }
