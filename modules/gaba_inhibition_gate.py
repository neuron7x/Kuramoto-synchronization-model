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


@dataclass
class GateState:
    gaba_fast: torch.Tensor            # fast component (A)
    gaba_slow: torch.Tensor            # slow component (B)
    risk_weight: torch.Tensor          # multiplicative scaler for action
    t_ms: torch.Tensor                 # internal time base (ms)


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
        # Normalize VIX-like to ~[0,1.5]; robust to outliers.
        return torch.clamp(vix / 40.0, 0.0, 1.5)

    def _cycles(self, t_ms: torch.Tensor) -> torch.Tensor:
        if not self.p.cycle_modulation:
            return torch.tensor(1.0, device=self.device)
        gamma = 0.2 * torch.sin(2 * math.pi * self.p.gamma_hz * (t_ms / 1000.0))
        theta = 0.15 * torch.sin(2 * math.pi * self.p.theta_hz * (t_ms / 1000.0))
        return 1.0 + gamma + theta

    # --- public API --------------------------------------------------------
    @torch.no_grad()
    def forward(
        self, market_state: Dict[str, torch.Tensor], action: torch.Tensor
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        # Ensure device/shape
        action = action.to(self.device)
        vix = market_state['vix'].to(self.device).reshape(1)
        vol = market_state['vol'].to(self.device).reshape(1)
        ret = market_state['ret'].to(self.device).reshape(1)
        rpe = market_state['rpe'].to(self.device).reshape(1)
        pos = market_state['pos'].to(self.device).reshape(1)
        delta_t_ms = market_state['delta_t_ms'].to(self.device).reshape(1)

        # 1) GABA release ~ threat proxy (volatility) with dual time constants
        drive = 0.5 * self._norm_vol(vix)
        self.gaba_fast = self.gaba_fast * self.decay_fast + drive * (1 - self.decay_fast)
        self.gaba_slow = self.gaba_slow * self.decay_slow + drive * (1 - self.decay_slow)
        gaba_level = torch.clamp(self.gaba_fast + 0.5 * self.gaba_slow, 0.0, 2.0)

        # 2) Inhibition proportional to GABA and action magnitude
        firing_proxy = torch.clamp(action.norm().unsqueeze(0), 0.0, 10.0)
        inhibition = self.p.k_inhibit * gaba_level * torch.tanh(firing_proxy)
        inhibition = torch.clamp(inhibition, 0.0, 0.95)

        # 3) Cycle modulation (gamma/theta)
        self.t_ms = self.t_ms + self.dt_tensor
        cyc = self._cycles(self.t_ms)

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
            dw = dw + 0.01 * gaba_level
        elif (pre_post < self.p.ltd_theta).item():
            dw = dw - 0.008 * gaba_level
        self.risk_weight = torch.clamp(self.risk_weight + dw, self.p.risk_min, self.p.risk_max)

        # 5) Apply gating
        gated = action * (1 - inhibition) * self.risk_weight * cyc

        metrics = {
            'inhibition': float(inhibition.item()),
            'gaba_level': float(gaba_level.item()),
            'risk_weight': float(self.risk_weight.item()),
        }
        return gated, metrics

    @torch.no_grad()
    def apply_hedge(self, strength: float = 1.0, half_life_h: float = 24.0):
        """Diazepam-analog hedge: transiently boost GABA and reduce sensitivity.
        strength in [0, 2].
        """
        boost = torch.tensor(strength, device=self.device)
        self.gaba_fast = torch.clamp(self.gaba_fast * (1 + 0.5 * boost), 0.0, 2.0)
        self.gaba_slow = torch.clamp(self.gaba_slow * (1 + 0.25 * boost), 0.0, 2.0)
