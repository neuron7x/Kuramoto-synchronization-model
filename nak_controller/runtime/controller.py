"""Runtime orchestration for the NaK neuro-energetic controller.

The controller coordinates per-strategy state updates, neuromodulator effects
and safety invariants while maintaining deterministic behaviour for testing.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Optional, TypedDict

import numpy as np

from ..conf.schema import load_nak_params
from ..control.global_mode import band_expand_for_mode, choose_mode
from ..control.neuromods import (
    acetylcholine,
    dopamine,
    modulate_activity_ach,
    modulate_risk_da,
    noradrenaline,
    serotonin,
)
from ..control.pi import pi_control, rate_limit
from ..core.energetics import compute_EI, update_energy, update_load
from ..core.params import NaKParams
from ..core.state import DiagnosticsSnapshot, Mode, StrategyState

LOGGER = logging.getLogger(__name__)


class BaseLimits(TypedDict):
    """Base limits supplied by the integration layer."""

    risk_per_trade_base: float
    max_position_base: float
    cooldown_ms_base: int


@dataclass(frozen=True)
class NaKStepOutput:
    """Dataclass returned by :meth:`NaKController.step`."""

    strategy_id: str
    risk_per_trade_factor: float
    max_position_factor: float
    cooldown_ms: int
    is_suspended: bool
    health: float
    EI: float
    E: float
    L: float
    mode: Mode
    diagnostics: DiagnosticsSnapshot

    def as_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["diagnostics"] = asdict(self.diagnostics)
        return payload


class NaKController:
    """Coordinate NaK updates for every strategy identifier."""

    def __init__(self, config_path: str, *, seed: Optional[int] = None):
        self.config_path = config_path
        self.p: NaKParams = load_nak_params(config_path)
        self.states: Dict[str, StrategyState] = {}
        self._initial_seed = seed
        self._rng = np.random.default_rng(seed)

    def reset(self, *, seed: Optional[int] = None) -> None:
        """Reset controller state and optionally reseed the noise generator."""

        if seed is not None:
            self._initial_seed = seed
        resolved_seed = self._initial_seed
        self.states.clear()
        self._rng = np.random.default_rng(resolved_seed)

    def get_state(self, sid: str) -> StrategyState:
        if sid not in self.states:
            self.states[sid] = StrategyState()
        return self.states[sid]

    def step(
        self,
        sid: str,
        local_obs: Mapping[str, float],
        global_obs: Mapping[str, float],
        bases: BaseLimits,
    ) -> NaKStepOutput:
        st = self.get_state(sid)
        p = self.p

        unexp = float(global_obs.get("unexpected_reward", 0.0))
        DA = dopamine(unexp, p.beta_DA)
        NA = noradrenaline(global_obs.get("global_vol", 0.0), p.na_vol_gain)
        HT = serotonin(global_obs.get("portfolio_dd", 0.0), p.ht_dd_gain)
        ACh = acetylcholine(global_obs.get("exposure", 0.0), p.eta_ACh)

        local_dict = dict(local_obs)

        update_load(st, p, local_dict, NA=NA, rng=self._rng)
        update_energy(st, p, local_dict, NA=NA, DA=DA, da_unexp=unexp)
        compute_EI(st, p, local_dict)

        mode = choose_mode(
            global_vol=float(global_obs.get("global_vol", 0.0)),
            portfolio_dd=float(global_obs.get("portfolio_dd", 0.0)),
            vol_amber=p.vol_amber,
            vol_red=p.vol_red,
            dd_amber=p.dd_amber,
            dd_red=p.dd_red,
        )
        band_exp = band_expand_for_mode(mode, p.band_GREEN, p.band_AMBER, p.band_RED)

        err, integ, r_tilde = pi_control(st, p, band_expand=band_exp)
        r_local = modulate_risk_da(r_tilde, DA, p.da_gain, p.r_min, p.r_max)

        risk_mult = dict(GREEN=p.risk_GREEN, AMBER=p.risk_AMBER, RED=p.risk_RED)[mode]
        act_mult = dict(GREEN=p.act_GREEN, AMBER=p.act_AMBER, RED=p.act_RED)[mode]

        r_after_mode = r_local * risk_mult
        activity = modulate_activity_ach(act_mult, ACh)
        r_limited = rate_limit(
            prev=st.last_risk,
            target=r_after_mode,
            limit=p.delta_r_limit,
            lo=p.r_min,
            hi=p.r_max,
        )

        EI_norm = st.EI
        f_freq = max(p.f_min, min(p.f_max, EI_norm * activity))
        min_cooldown = int(math.floor(bases["cooldown_ms_base"] / max(p.f_max, 1e-9)))
        cooldown_ms = int(max(min_cooldown, bases["cooldown_ms_base"] / max(f_freq, 1e-9)))

        unsuspend_threshold = p.EI_crit + p.EI_hysteresis
        if st.suspended:
            suspended = EI_norm < unsuspend_threshold or (risk_mult == 0.0)
        else:
            suspended = EI_norm < p.EI_crit or (risk_mult == 0.0)

        risk_factor = r_limited if not suspended else p.r_min
        maxpos_factor = risk_factor

        diagnostics = DiagnosticsSnapshot(
            err=err,
            integral=integ,
            r_tilde=r_tilde,
            r_local=r_local,
            dopamine=DA,
            noradrenaline=NA,
            serotonin=HT,
            acetylcholine=ACh,
            mode=mode,
            risk_mult=risk_mult,
            activity=activity,
            band_expansion=band_exp,
            frequency=f_freq,
        )

        st.suspended = suspended
        st.last_risk = risk_factor
        st.last = diagnostics

        assert p.r_min - 1e-9 <= risk_factor <= p.r_max + 1e-9
        assert math.isclose(risk_factor, maxpos_factor, rel_tol=1e-9, abs_tol=1e-9)
        if mode == "RED":
            assert suspended or math.isclose(risk_mult, 0.0, abs_tol=1e-9)
        assert cooldown_ms >= min_cooldown

        output = NaKStepOutput(
            strategy_id=sid,
            risk_per_trade_factor=risk_factor,
            max_position_factor=maxpos_factor,
            cooldown_ms=cooldown_ms,
            is_suspended=suspended,
            health=st.health,
            EI=st.EI,
            E=st.E,
            L=st.L,
            mode=mode,
            diagnostics=diagnostics,
        )

        LOGGER.debug("nak_step", extra={"nak_output": output.as_dict()})

        return output


__all__ = ["NaKController", "NaKStepOutput", "BaseLimits"]
