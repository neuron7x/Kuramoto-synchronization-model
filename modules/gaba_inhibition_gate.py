# Copyright (c) 2025 TradePulse
# SPDX-License-Identifier: Apache-2.0
# Biophysical gate mapping GABAergic inhibition to risk-aware action modulation.
# Primary sources: Buzsáki & Wang (2012); Bliss & Collingridge (1993);
# Bi & Poo (1998); Bowery et al. (2002)

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Tuple, Optional

import torch
import torch.nn as nn

# Constants for biophysical parameters
_VIX_NORMALIZATION_FACTOR = 40.0  # VIX baseline for normalization
_GABA_DRIVE_SCALE = 0.5           # Scale factor for volatility->GABA conversion
_GABA_SLOW_WEIGHT = 0.5           # Weight of slow GABA_B in total level
_GABA_MAX_LEVEL = 2.0             # Maximum combined GABA level
_FIRING_PROXY_MAX = 10.0          # Maximum action magnitude for inhibition
_GAMMA_CYCLE_AMPLITUDE = 0.2      # Amplitude of gamma oscillation
_THETA_CYCLE_AMPLITUDE = 0.15     # Amplitude of theta oscillation
_MS_TO_SECONDS = 1000.0           # Conversion factor
_LTP_STRENGTH = 0.01              # LTP weight increment
_LTD_STRENGTH = 0.008             # LTD weight decrement
_HEDGE_FAST_BOOST = 0.5           # Fast GABA boost factor in hedge
_HEDGE_SLOW_BOOST = 0.25          # Slow GABA boost factor in hedge


@dataclass
class GateParams:
    v_rest: float = -70.0
    v_threshold: float = -55.0
    tau_gaba_a_ms: float = 8.0        # fast inhibition (~GABA_A)
    tau_gaba_b_ms: float = 100.0      # slow inhibition (~GABA_B)
    gamma_hz: float = 40.0
    theta_hz: float = 8.0
    k_inhibit: float = 0.4            # inhibition gain
    stdp_a_plus: float = 0.008
    stdp_a_minus: float = 0.006
    stdp_tau_plus_ms: float = 16.8
    stdp_tau_minus_ms: float = 33.7
    ltp_theta: float = 0.3
    ltd_theta: float = 0.1
    dt_ms: float = 0.1                # simulation step in milliseconds
    risk_min: float = 0.5             # clamp for risk weight
    risk_max: float = 1.5
    cycle_modulation: bool = True
    enforce_mfd: bool = True          # MFD guarantee: gated action ≤ input action magnitude


@dataclass
class GateState:
    gaba_fast: torch.Tensor            # fast component (A)
    gaba_slow: torch.Tensor            # slow component (B)
    risk_weight: torch.Tensor          # multiplicative scaler for action
    t_ms: torch.Tensor                 # internal time base (ms)


@dataclass
class GateMetrics:
    """Metrics returned by GABAInhibitionGate forward pass."""
    inhibition: float
    gaba_level: float
    risk_weight: float


class GABAInhibitionGate(nn.Module):
    """Maps threat → inhibition; cycles → modulation; timing → plasticity.

    Inputs
    ------
    market_state : Dict[str, torch.Tensor]
        Required keys: 'vol', 'ret', 'vix', 'pos', 'rpe', 'delta_t_ms'.
    action : torch.Tensor
        Proposed action vector (e.g., position deltas). Shape (N,) or scalar.

    Outputs
    -------
    gated_action : torch.Tensor
    metrics : Dict[str, float] with keys: 'inhibition', 'gaba_level', 'risk_weight'.
    """

    def __init__(self, params: Optional[GateParams] = None, device: Optional[str] = None):
        super().__init__()
        self.p = params or GateParams()
        dev = device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(dev)
        self.register_buffer("gaba_fast", torch.zeros(1, dtype=torch.float32, device=self.device))
        self.register_buffer("gaba_slow", torch.zeros(1, dtype=torch.float32, device=self.device))
        self.register_buffer("risk_weight", torch.ones(1, dtype=torch.float32, device=self.device))
        self.register_buffer("t_ms", torch.zeros(1, dtype=torch.float32, device=self.device))

        # precompute decay factors per step
        self.register_buffer("decay_fast", self._compute_decay(self.p.tau_gaba_a_ms))
        self.register_buffer("decay_slow", self._compute_decay(self.p.tau_gaba_b_ms))
        
        # precompute dt tensor for efficiency
        self.register_buffer("dt_tensor", torch.tensor(self.p.dt_ms, device=self.device))

    # --- helpers -----------------------------------------------------------
    def _compute_decay(self, tau_ms: float) -> torch.Tensor:
        """Compute exponential decay factor for given time constant."""
        return torch.exp(torch.tensor(-self.p.dt_ms / tau_ms, device=self.device))
    
    def _norm_vol(self, vix: torch.Tensor) -> torch.Tensor:
        """Normalize VIX-like to ~[0,1.5]; robust to outliers."""
        return torch.clamp(vix / _VIX_NORMALIZATION_FACTOR, 0.0, 1.5)

    def _cycles(self, t_ms: torch.Tensor) -> torch.Tensor:
        """Compute gamma/theta cycle modulation."""
        if not self.p.cycle_modulation:
            return torch.tensor(1.0, device=self.device)
        t_seconds = t_ms / _MS_TO_SECONDS
        gamma = _GAMMA_CYCLE_AMPLITUDE * torch.sin(2 * math.pi * self.p.gamma_hz * t_seconds)
        theta = _THETA_CYCLE_AMPLITUDE * torch.sin(2 * math.pi * self.p.theta_hz * t_seconds)
        return 1.0 + gamma + theta

    # --- public API --------------------------------------------------------
    @torch.no_grad()
    def forward(
        self, market_state: Dict[str, torch.Tensor], action: torch.Tensor
    ) -> Tuple[torch.Tensor, GateMetrics]:
        """Apply GABA inhibition gate to action.
        
        Parameters
        ----------
        market_state : Dict[str, torch.Tensor]
            Market state with keys: 'vix', 'vol', 'ret', 'pos', 'rpe', 'delta_t_ms'
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
        required_keys = ['vix', 'vol', 'ret', 'pos', 'rpe', 'delta_t_ms']
        missing_keys = [k for k in required_keys if k not in market_state]
        if missing_keys:
            raise KeyError(f"Missing required keys in market_state: {missing_keys}")
        
        # Validate market_state tensors for NaN/Inf
        for k in required_keys:
            t = market_state[k].to(self.device)
            if torch.isnan(t).any() or torch.isinf(t).any():
                raise ValueError(f"{k} contains NaN or Inf values")
        
        # Ensure device/shape
        action = action.to(self.device)
        if torch.isnan(action).any() or torch.isinf(action).any():
            raise ValueError("action contains NaN or Inf values")
            
        vix = market_state['vix'].to(self.device).reshape(1)
        vol = market_state['vol'].to(self.device).reshape(1)
        ret = market_state['ret'].to(self.device).reshape(1)
        _rpe = market_state['rpe'].to(self.device).reshape(1)  # Reserved for future use
        _pos = market_state['pos'].to(self.device).reshape(1)  # Reserved for future use
        delta_t_ms = market_state['delta_t_ms'].to(self.device).reshape(1)

        # 1) GABA release ~ threat proxy (volatility) with dual time constants
        drive = _GABA_DRIVE_SCALE * self._norm_vol(vix)
        self.gaba_fast = self.gaba_fast * self.decay_fast + drive * (1 - self.decay_fast)
        self.gaba_slow = self.gaba_slow * self.decay_slow + drive * (1 - self.decay_slow)
        gaba_level = torch.clamp(
            self.gaba_fast + _GABA_SLOW_WEIGHT * self.gaba_slow, 0.0, _GABA_MAX_LEVEL
        )

        # 2) Inhibition proportional to GABA and action magnitude
        firing_proxy = torch.clamp(action.norm().unsqueeze(0), 0.0, _FIRING_PROXY_MAX)
        inhibition = self.p.k_inhibit * gaba_level * torch.tanh(firing_proxy)
        inhibition = torch.clamp(inhibition, 0.0, 0.95)

        # 3) Cycle modulation (gamma/theta)
        if self.p.cycle_modulation:
            self.t_ms = self.t_ms + self.dt_tensor
            cyc = self._cycles(self.t_ms)
        else:
            cyc = torch.tensor(1.0, device=self.device)

        # 4) Plasticity (STDP + LTP/LTD)
        # Ensure delta_t_ms is scalar for conditional
        delta_t_scalar = delta_t_ms.squeeze()
        if (delta_t_scalar > 0).item():
            dw = (
                self.p.stdp_a_plus
                * torch.exp(-delta_t_ms / self.p.stdp_tau_plus_ms)
                * gaba_level
            )
        else:
            dw = (
                -self.p.stdp_a_minus
                * torch.exp(delta_t_ms / self.p.stdp_tau_minus_ms)
                * gaba_level
            )
        # LTP/LTD gated by vol*ret (pre*post)
        pre_post = vol * ret
        if (pre_post > self.p.ltp_theta).item():
            dw = dw + _LTP_STRENGTH * gaba_level
        elif (pre_post < self.p.ltd_theta).item():
            dw = dw - _LTD_STRENGTH * gaba_level
        self.risk_weight = torch.clamp(self.risk_weight + dw, self.p.risk_min, self.p.risk_max)

        # 5) Apply gating
        gated = action * (1 - inhibition) * self.risk_weight * cyc
        
        # 6) MFD guarantee: if GABA is elevated, ensure gated action doesn't exceed input
        if self.p.enforce_mfd and (gaba_level > 0.1).item():
            gated = torch.where(gated.abs() > action.abs(), action, gated)

        return gated, GateMetrics(
            inhibition=float(inhibition.item()),
            gaba_level=float(gaba_level.item()),
            risk_weight=float(self.risk_weight.item())
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
            t_ms=self.t_ms.clone()
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
        self.gaba_fast = torch.clamp(
            self.gaba_fast * (1 + _HEDGE_FAST_BOOST * boost), 0.0, _GABA_MAX_LEVEL
        )
        self.gaba_slow = torch.clamp(
            self.gaba_slow * (1 + _HEDGE_SLOW_BOOST * boost), 0.0, _GABA_MAX_LEVEL
        )
