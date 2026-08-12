# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# Biophysical gate mapping GABAergic inhibition to risk-aware action modulation.
# Primary sources: Buzsáki & Wang (2012); Bliss & Collingridge (1993);
# Bi & Poo (1998); Bowery et al. (2002)

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Optional, Tuple

import torch
import torch.nn as nn

from modules.types import MarketState

_MS_TO_SECONDS = 1000.0  # Conversion factor


@dataclass
class GateParams:
    v_rest: float = -70.0
    v_threshold: float = -55.0
    tau_gaba_a_ms: float = 8.0  # fast inhibition (~GABA_A)
    tau_gaba_b_ms: float = 100.0  # slow inhibition (~GABA_B)
    gamma_hz: float = 40.0
    theta_hz: float = 8.0
    k_inhibit: float = 0.4  # inhibition gain
    stdp_a_plus: float = 0.008
    stdp_a_minus: float = 0.006
    stdp_tau_plus_ms: float = 16.8
    stdp_tau_minus_ms: float = 33.7
    ltp_theta: float = 0.3
    ltd_theta: float = 0.1
    dt_ms: float = 0.1  # default simulation step in milliseconds
    min_dt_ms: float = 1e-3  # minimum allowed dt for stability
    max_dt_ms: float = 250.0  # cap dt to avoid numerical blowups
    risk_min: float = 0.5  # clamp for risk weight
    risk_max: float = 1.5
    cycle_modulation: bool = True
    enforce_mfd: bool = True  # MFD guarantee: gated action ≤ input action magnitude
    vix_norm: float = 40.0  # VIX baseline for normalization
    vix_clip_max: float = 1.5  # Maximum normalized VIX
    gaba_drive_scale: float = 0.5  # Scale factor for volatility->GABA conversion
    gaba_slow_weight: float = 0.5  # Weight of slow GABA_B in total level
    gaba_max_level: float = 2.0  # Maximum combined GABA level
    firing_proxy_max: float = 10.0  # Maximum action magnitude for inhibition
    gamma_cycle_amplitude: float = 0.2
    theta_cycle_amplitude: float = 0.15
    ltp_strength: float = 0.01  # LTP weight increment
    ltd_strength: float = 0.008  # LTD weight decrement
    max_inhibition: float = 0.95  # Upper bound for inhibition factor
    hedge_fast_boost: float = 0.5  # Fast GABA boost factor in hedge
    hedge_slow_boost: float = 0.25  # Slow GABA boost factor in hedge
    hedge_risk_damp: float = 0.25  # Risk-weight damping factor during hedge
    risk_decay_tau_ms: float = 500.0  # Relax risk weight back to baseline
    rpe_sensitivity: float = 0.05  # Reward prediction error effect on plasticity
    position_sensitivity: float = 0.02  # Exposure-based dampener

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate parameter ranges to avoid unstable simulations."""

        if self.dt_ms <= 0:
            raise ValueError("dt_ms must be positive")
        if self.tau_gaba_a_ms <= 0 or self.tau_gaba_b_ms <= 0:
            raise ValueError("GABA time constants must be positive")
        if self.gamma_hz <= 0 or self.theta_hz <= 0:
            raise ValueError("Oscillation frequencies must be positive")
        if self.k_inhibit < 0:
            raise ValueError("k_inhibit must be non-negative")
        if self.stdp_a_plus < 0 or self.stdp_a_minus < 0:
            raise ValueError("STDP coefficients must be non-negative")
        if self.stdp_tau_plus_ms <= 0 or self.stdp_tau_minus_ms <= 0:
            raise ValueError("STDP time constants must be positive")
        if self.ltp_strength < 0 or self.ltd_strength < 0:
            raise ValueError("Plasticity strengths must be non-negative")
        if not (self.risk_min <= self.risk_max):
            raise ValueError("risk_min must be <= risk_max")
        if self.vix_norm <= 0:
            raise ValueError("vix_norm must be positive")
        if self.vix_clip_max <= 0:
            raise ValueError("vix_clip_max must be positive")
        if self.gaba_drive_scale < 0:
            raise ValueError("gaba_drive_scale must be non-negative")
        if self.gaba_slow_weight < 0:
            raise ValueError("gaba_slow_weight must be non-negative")
        if self.gaba_max_level <= 0:
            raise ValueError("gaba_max_level must be positive")
        if self.firing_proxy_max <= 0:
            raise ValueError("firing_proxy_max must be positive")
        if self.gamma_cycle_amplitude < 0 or self.theta_cycle_amplitude < 0:
            raise ValueError("Cycle amplitudes must be non-negative")
        if not (0 < self.max_inhibition < 1):
            raise ValueError("max_inhibition must be in (0, 1)")
        if self.hedge_fast_boost < 0 or self.hedge_slow_boost < 0:
            raise ValueError("hedge boost factors must be non-negative")
        if self.hedge_risk_damp < 0:
            raise ValueError("hedge_risk_damp must be non-negative")
        if self.risk_decay_tau_ms <= 0:
            raise ValueError("risk_decay_tau_ms must be positive")
        if self.min_dt_ms <= 0:
            raise ValueError("min_dt_ms must be positive")
        if self.max_dt_ms <= 0:
            raise ValueError("max_dt_ms must be positive")
        if self.min_dt_ms > self.max_dt_ms:
            raise ValueError("min_dt_ms must be <= max_dt_ms")
        if self.rpe_sensitivity < 0:
            raise ValueError("rpe_sensitivity must be non-negative")
        if self.position_sensitivity < 0:
            raise ValueError("position_sensitivity must be non-negative")

    def as_dict(self) -> Dict[str, Any]:
        """Return a configuration dictionary for serialization."""

        return asdict(self)

    def copy_with(self, **overrides: Any) -> "GateParams":
        """Create a copy with overridden fields while re-validating."""

        base = self.as_dict()
        base.update(overrides)
        return GateParams(**base)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GateParams":
        """Instantiate parameters from a dictionary, ignoring unknown keys."""

        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class GateState:
    gaba_fast: torch.Tensor  # fast component (A)
    gaba_slow: torch.Tensor  # slow component (B)
    risk_weight: torch.Tensor  # multiplicative scaler for action
    t_ms: torch.Tensor  # internal time base (ms)


@dataclass
class GateMetrics:
    """Metrics returned by :class:`GABAInhibitionGate` forward pass."""

    inhibition: float
    gaba_level: float
    risk_weight: float
    cycle_multiplier: float
    stdp_delta: float
    ltp_ltd_delta: float
    adaptive_delta: float


class GABAInhibitionGate(nn.Module):
    """Maps threat → inhibition; cycles → modulation; timing → plasticity.

    Inputs
    ------
    market_state : MarketState
        Required keys: 'volatility', 'return', 'vix', 'position', 'rpe', 'delta_t_ms'.
    action : torch.Tensor
        Proposed action vector (e.g., position deltas). Shape (N,) or scalar.

    Outputs
    -------
    gated_action : torch.Tensor
    metrics : Dict[str, float] with keys: 'inhibition', 'gaba_level', 'risk_weight',
        'cycle_multiplier', 'stdp_delta', 'ltp_ltd_delta', 'adaptive_delta'.
    """

    # Type annotations for registered buffers
    gaba_fast: torch.Tensor
    gaba_slow: torch.Tensor
    risk_weight: torch.Tensor
    t_ms: torch.Tensor
    decay_fast: torch.Tensor
    decay_slow: torch.Tensor

    def __init__(self, params: Optional[GateParams] = None, device: Optional[str] = None):
        super().__init__()
        self.p = params or GateParams()
        dev = device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(dev)
        self.register_buffer("gaba_fast", torch.zeros(1, dtype=torch.float32, device=self.device))
        self.register_buffer("gaba_slow", torch.zeros(1, dtype=torch.float32, device=self.device))
        self.register_buffer("risk_weight", torch.ones(1, dtype=torch.float32, device=self.device))
        self.register_buffer("t_ms", torch.zeros(1, dtype=torch.float32, device=self.device))

        # buffers reflect the latest decay factors (useful for inspection/tests)
        self.register_buffer("decay_fast", torch.zeros(1, dtype=torch.float32, device=self.device))
        self.register_buffer("decay_slow", torch.zeros(1, dtype=torch.float32, device=self.device))
        self._refresh_precomputed_buffers()

    # --- helpers -----------------------------------------------------------
    def _compute_decay(self, dt_ms: torch.Tensor, tau_ms: float) -> torch.Tensor:
        """Compute exponential decay factor for the provided time constant and dt."""
        return torch.exp(-dt_ms / tau_ms)

    def _clamp_dt(self, delta_t_ms: torch.Tensor) -> torch.Tensor:
        """Clamp the spike-timing delta to a numerically stable integration dt."""
        dt = delta_t_ms.abs()
        dt = torch.clamp(dt, self.p.min_dt_ms, self.p.max_dt_ms)
        return dt.to(device=self.device, dtype=torch.float32)

    def _norm_vol(self, vix: torch.Tensor) -> torch.Tensor:
        """Normalize VIX-like to ~[0,1.5]; robust to outliers."""
        return torch.clamp(vix / self.p.vix_norm, 0.0, self.p.vix_clip_max)

    def _cycles(self, t_ms: torch.Tensor) -> torch.Tensor:
        """Compute gamma/theta cycle modulation."""
        if not self.p.cycle_modulation:
            return torch.tensor(1.0, device=self.device)
        t_seconds = t_ms / _MS_TO_SECONDS
        gamma = self.p.gamma_cycle_amplitude * torch.sin(2 * math.pi * self.p.gamma_hz * t_seconds)
        theta = self.p.theta_cycle_amplitude * torch.sin(2 * math.pi * self.p.theta_hz * t_seconds)
        return 1.0 + gamma + theta

    def _refresh_precomputed_buffers(self) -> None:
        """Recompute decay coefficients and cached time step when params change."""

        with torch.no_grad():
            base_dt = torch.tensor(self.p.dt_ms, device=self.device, dtype=torch.float32)
            self.decay_fast.copy_(self._compute_decay(base_dt, self.p.tau_gaba_a_ms))
            self.decay_slow.copy_(self._compute_decay(base_dt, self.p.tau_gaba_b_ms))

    # --- public API --------------------------------------------------------
    @torch.no_grad()
    def forward(
        self, market_state: MarketState, action: torch.Tensor
    ) -> Tuple[torch.Tensor, GateMetrics]:
        """Apply GABA inhibition gate to action.

        Parameters
        ----------
        market_state : MarketState
            Market state with keys: 'vix', 'volatility', 'return', 'position', 'rpe',
            'delta_t_ms'
        action : torch.Tensor
            Proposed action vector

        Returns
        -------
        Tuple[torch.Tensor, GateMetrics]
            Gated action and metrics

        Raises
        ------
        KeyError
            If required keys missing from market_state
        ValueError
            If tensors have invalid values (NaN, Inf)
        """
        # Validate inputs
        required_keys = [
            "vix",
            "volatility",
            "return",
            "position",
            "rpe",
            "delta_t_ms",
        ]
        missing_keys = [k for k in required_keys if k not in market_state]
        if missing_keys:
            raise KeyError(f"Missing required keys in market_state: {missing_keys}")

        # Validate market_state values for NaN/Inf
        tensors: Dict[str, torch.Tensor] = {}
        for k in required_keys:
            t = torch.as_tensor(market_state[k], device=self.device, dtype=torch.float32)
            if torch.isnan(t).any() or torch.isinf(t).any():
                raise ValueError(f"{k} contains NaN or Inf values")
            tensors[k] = t

        # Ensure device/shape
        action = action.to(self.device)
        if torch.isnan(action).any() or torch.isinf(action).any():
            raise ValueError("action contains NaN or Inf values")

        vix = tensors["vix"].reshape(1)
        vol = tensors["volatility"].reshape(1)
        ret = tensors["return"].reshape(1)
        rpe = tensors["rpe"].reshape(1)
        pos = tensors["position"].reshape(1)
        delta_t_ms = tensors["delta_t_ms"].reshape(1)
        dt_ms = self._clamp_dt(delta_t_ms)

        # 1) GABA release ~ threat proxy (volatility) with dual time constants
        drive = self.p.gaba_drive_scale * self._norm_vol(vix)
        decay_fast = self._compute_decay(dt_ms, self.p.tau_gaba_a_ms)
        decay_slow = self._compute_decay(dt_ms, self.p.tau_gaba_b_ms)
        self.decay_fast.copy_(decay_fast)
        self.decay_slow.copy_(decay_slow)
        new_gaba_fast = self.gaba_fast * decay_fast + drive * (1 - decay_fast)
        new_gaba_slow = self.gaba_slow * decay_slow + drive * (1 - decay_slow)
        self.gaba_fast.copy_(new_gaba_fast)
        self.gaba_slow.copy_(new_gaba_slow)
        gaba_level = torch.clamp(
            self.gaba_fast + self.p.gaba_slow_weight * self.gaba_slow,
            0.0,
            self.p.gaba_max_level,
        )

        # 2) Inhibition proportional to GABA and action magnitude
        firing_proxy = torch.clamp(action.norm().unsqueeze(0), 0.0, self.p.firing_proxy_max)
        inhibition = self.p.k_inhibit * gaba_level * torch.tanh(firing_proxy)
        inhibition = torch.clamp(inhibition, 0.0, self.p.max_inhibition)

        # 3) Cycle modulation (gamma/theta)
        if self.p.cycle_modulation:
            self.t_ms.add_(dt_ms)
            cyc = self._cycles(self.t_ms)
        else:
            cyc = torch.tensor(1.0, device=self.device)
        cycle_multiplier = float(cyc.item())

        # 4) Plasticity (STDP + LTP/LTD)
        # Ensure delta_t_ms is scalar for conditional
        delta_t_scalar = delta_t_ms.squeeze()
        if (delta_t_scalar > 0).item():
            stdp_component = (
                self.p.stdp_a_plus * torch.exp(-delta_t_ms / self.p.stdp_tau_plus_ms) * gaba_level
            )
        else:
            stdp_component = (
                -self.p.stdp_a_minus * torch.exp(delta_t_ms / self.p.stdp_tau_minus_ms) * gaba_level
            )
        # LTP/LTD gated by vol*ret (pre*post)
        pre_post = vol * ret
        ltp_ltd_component = torch.zeros_like(stdp_component)
        if (pre_post > self.p.ltp_theta).item():
            ltp_ltd_component = self.p.ltp_strength * gaba_level
        elif (pre_post < self.p.ltd_theta).item():
            ltp_ltd_component = -self.p.ltd_strength * gaba_level
        rpe_term = self.p.rpe_sensitivity * torch.tanh(rpe)
        exposure_term = self.p.position_sensitivity * torch.tanh(pos.abs())
        adaptive_term = (rpe_term - exposure_term) * gaba_level
        dw = stdp_component + ltp_ltd_component + adaptive_term
        baseline = torch.tensor(1.0, device=self.device)
        relax = self._compute_decay(dt_ms, self.p.risk_decay_tau_ms)
        relaxed_weight = baseline + (self.risk_weight - baseline) * relax
        new_risk_weight = relaxed_weight + dw
        new_risk_weight = torch.clamp(new_risk_weight, self.p.risk_min, self.p.risk_max)
        self.risk_weight.copy_(new_risk_weight)

        # 5) Apply gating
        gated = action * (1 - inhibition) * self.risk_weight * cyc

        # 6) MFD guarantee: if GABA is elevated, ensure gated action doesn't exceed input
        if self.p.enforce_mfd and (gaba_level > 0.1).item():
            gated = torch.where(gated.abs() > action.abs(), action, gated)

        return gated, GateMetrics(
            inhibition=float(inhibition.item()),
            gaba_level=float(gaba_level.item()),
            risk_weight=float(self.risk_weight.item()),
            cycle_multiplier=cycle_multiplier,
            stdp_delta=float(stdp_component.item()),
            ltp_ltd_delta=float(ltp_ltd_component.item()),
            adaptive_delta=float(adaptive_term.item()),
        )

    def get_state(self) -> GateState:
        """Get current gate state.

        Returns
        -------
        GateState
            Current internal state of the gate
        """
        return GateState(
            gaba_fast=self.gaba_fast.clone(),
            gaba_slow=self.gaba_slow.clone(),
            risk_weight=self.risk_weight.clone(),
            t_ms=self.t_ms.clone(),
        )

    def set_state(self, state: GateState) -> None:
        """Set gate state.

        Parameters
        ----------
        state : GateState
            State to restore
        """
        with torch.no_grad():
            self.gaba_fast.copy_(state.gaba_fast.to(self.device))
            self.gaba_slow.copy_(state.gaba_slow.to(self.device))
            self.risk_weight.copy_(state.risk_weight.to(self.device))
            self.t_ms.copy_(state.t_ms.to(self.device))

    @torch.no_grad()
    def reset_state(self) -> None:
        """Reset gate state to initial equilibrium values."""

        self.gaba_fast.zero_()
        self.gaba_slow.zero_()
        self.risk_weight.fill_(1.0)
        self.t_ms.zero_()

    @torch.no_grad()
    def apply_hedge(self, strength: float = 1.0) -> None:
        """Diazepam-analog hedge: transiently boost GABA and reduce sensitivity.

        Parameters
        ----------
        strength : float, optional
            Hedge strength multiplier in [0, 2], by default 1.0
            Higher values increase GABAergic inhibition.
        """
        if not 0.0 <= strength <= 2.0:
            raise ValueError(f"strength must be in [0, 2], got {strength}")

        boost = torch.tensor(strength, device=self.device)
        boosted_fast = torch.clamp(
            self.gaba_fast * (1 + self.p.hedge_fast_boost * boost),
            0.0,
            self.p.gaba_max_level,
        )
        boosted_slow = torch.clamp(
            self.gaba_slow * (1 + self.p.hedge_slow_boost * boost),
            0.0,
            self.p.gaba_max_level,
        )
        self.gaba_fast.copy_(boosted_fast)
        self.gaba_slow.copy_(boosted_slow)
        damp = 1.0 / (1 + self.p.hedge_risk_damp * boost)
        new_weight = torch.clamp(self.risk_weight * damp, self.p.risk_min, self.p.risk_max)
        self.risk_weight.copy_(new_weight)

    def configure(self, params: Optional[GateParams] = None, **overrides: Any) -> None:
        """Update gate parameters at runtime and refresh cached buffers.

        Parameters
        ----------
        params : GateParams, optional
            Complete parameter bundle to install.
        **overrides : Any
            Individual parameter overrides merged with existing configuration.
        """

        if params is not None and overrides:
            raise ValueError("Specify either params or overrides, not both")

        if params is not None:
            self.p = params
        elif overrides:
            self.p = self.p.copy_with(**overrides)

        self._refresh_precomputed_buffers()

    @classmethod
    def from_config(
        cls, config: Dict[str, Any], device: Optional[str] = None
    ) -> "GABAInhibitionGate":
        """Construct a gate directly from a configuration dictionary."""

        params = GateParams.from_dict(config)
        return cls(params=params, device=device)

    def to_config(self) -> Dict[str, Any]:
        """Return the current configuration dictionary."""

        return self.p.as_dict()
