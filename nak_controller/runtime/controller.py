"""Runtime NaK controller implementation."""
from __future__ import annotations

from typing import Any, Dict

import yaml  # type: ignore[import-untyped]

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
from ..core.config import load_validated
from ..core.energetics import compute_EI, update_energy, update_load
from ..core.params import NaKParams
from ..core.state import StrategyState


class NaKController:
    """Per-strategy NaK control loop."""

    def __init__(self, config_path: str) -> None:
        with open(config_path, "r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        cfg = load_validated(raw["nak"])

        self.params = NaKParams(
            L_min=cfg.L_min,
            L_max=cfg.L_max,
            E_max=cfg.E_max,
            EI_low=cfg.EI_low,
            EI_high=cfg.EI_high,
            EI_crit=cfg.EI_crit,
            EI_hysteresis=cfg.EI_hysteresis,
            I_max=cfg.I_max,
            r_min=cfg.r_min,
            r_max=cfg.r_max,
            f_min=cfg.f_min,
            f_max=cfg.f_max,
            delta_r_limit=cfg.delta_r_limit,
            w_n=cfg.w_n,
            w_v=cfg.w_v,
            w_d=cfg.w_d,
            w_e=cfg.w_e,
            w_l=cfg.w_l,
            w_s=cfg.w_s,
            a_p=cfg.a_p,
            a_n=cfg.a_n,
            a_v=cfg.a_v,
            a_g=cfg.a_g,
            a_da=cfg.a_da,
            u_e=cfg.u_e,
            u_l=cfg.u_l,
            u_p=cfg.u_p,
            Kp=cfg.Kp,
            Ki=cfg.Ki,
            beta_DA=cfg.beta_DA,
            eta_ACh=cfg.eta_ACh,
            da_gain=cfg.da_gain,
            na_vol_gain=cfg.na_vol_gain,
            na_scale=cfg.na_scale,
            ht_dd_gain=cfg.ht_dd_gain,
            vol_amber=cfg.vol_amber,
            vol_red=cfg.vol_red,
            dd_amber=cfg.dd_amber,
            dd_red=cfg.dd_red,
            risk_GREEN=cfg.risk_mult.GREEN,
            risk_AMBER=cfg.risk_mult.AMBER,
            risk_RED=cfg.risk_mult.RED,
            act_GREEN=cfg.activity_mult.GREEN,
            act_AMBER=cfg.activity_mult.AMBER,
            act_RED=cfg.activity_mult.RED,
            band_GREEN=cfg.band_expand.GREEN,
            band_AMBER=cfg.band_expand.AMBER,
            band_RED=cfg.band_expand.RED,
            noise_sigma=cfg.noise_sigma,
        )
        self.states: Dict[str, StrategyState] = {}

    def reset(self) -> None:
        """Reset all strategy states (useful for deterministic tests)."""

        self.states.clear()

    def get_state(self, strategy_id: str) -> StrategyState:
        if strategy_id not in self.states:
            self.states[strategy_id] = StrategyState()
        return self.states[strategy_id]

    def step(
        self,
        strategy_id: str,
        local_obs: Dict[str, float],
        global_obs: Dict[str, float],
        bases: Dict[str, float],
    ) -> Dict[str, Any]:
        """Advance the controller one step for *strategy_id*."""

        state = self.get_state(strategy_id)
        params = self.params

        unexpected_reward = float(global_obs.get("unexpected_reward", 0.0))
        dopamine_level = dopamine(unexpected_reward, params.beta_DA)
        noradrenaline_level = noradrenaline(global_obs.get("global_vol", 0.0), params.na_vol_gain)
        serotonin_level = serotonin(global_obs.get("portfolio_dd", 0.0), params.ht_dd_gain)
        acetylcholine_level = acetylcholine(global_obs.get("exposure", 0.0), params.eta_ACh)

        update_load(state, params, local_obs, NA=noradrenaline_level)
        update_energy(
            state,
            params,
            local_obs,
            NA=noradrenaline_level,
            DA=dopamine_level,
            da_unexpected=unexpected_reward,
        )
        compute_EI(state, params, local_obs)

        mode = choose_mode(
            global_obs.get("global_vol", 0.0),
            global_obs.get("portfolio_dd", 0.0),
            params.vol_amber,
            params.vol_red,
            params.dd_amber,
            params.dd_red,
        )
        band_expand = band_expand_for_mode(mode, params.band_GREEN, params.band_AMBER, params.band_RED)
        error, integral, r_tilde = pi_control(state, params, band_expand=band_expand)

        risk_local = modulate_risk_da(r_tilde, dopamine_level, params.da_gain, params.r_min, params.r_max)
        risk_mult_map: Dict[str, float] = {
            "GREEN": params.risk_GREEN,
            "AMBER": params.risk_AMBER,
            "RED": params.risk_RED,
        }
        activity_map: Dict[str, float] = {
            "GREEN": params.act_GREEN,
            "AMBER": params.act_AMBER,
            "RED": params.act_RED,
        }
        risk_mult = risk_mult_map[mode]
        activity_mult = activity_map[mode]

        risk_after_mode = risk_local * risk_mult
        limited_risk = rate_limit(
            prev=state.last_risk,
            target=risk_after_mode,
            limit=params.delta_r_limit,
            lo=params.r_min,
            hi=params.r_max,
        )
        activity = modulate_activity_ach(activity_mult, acetylcholine_level)

        ei_norm = state.EI
        frequency = max(params.f_min, min(params.f_max, ei_norm * activity))
        cooldown_ms_base = bases.get("cooldown_ms_base", 1000.0)
        cooldown_ms = int(max(1.0, cooldown_ms_base / max(1e-9, frequency)))
        unsuspend_threshold = params.EI_crit + params.EI_hysteresis
        if state.suspended:
            suspended = ei_norm < unsuspend_threshold or risk_mult == 0.0
        else:
            suspended = ei_norm < params.EI_crit or risk_mult == 0.0

        risk_factor = limited_risk if not suspended else params.r_min
        maxpos_factor = risk_factor

        assert params.r_min <= risk_factor <= params.r_max
        assert maxpos_factor == risk_factor
        assert cooldown_ms >= int(cooldown_ms_base / max(1e-9, params.f_max))
        if mode == "RED":
            assert suspended or risk_mult == 0.0

        state.suspended = suspended
        state.last_risk = risk_factor
        state.last = {
            "err": error,
            "I": integral,
            "r_tilde": r_tilde,
            "r_local": risk_local,
            "DA": dopamine_level,
            "NA": noradrenaline_level,
            "5HT": serotonin_level,
            "ACh": acetylcholine_level,
            "mode": mode,
            "risk_mult": risk_mult,
            "activity": activity,
            "band_exp": band_expand,
            "f_freq": frequency,
        }

        return {
            "strategy_id": strategy_id,
            "risk_per_trade_factor": risk_factor,
            "max_position_factor": maxpos_factor,
            "cooldown_ms": cooldown_ms,
            "is_suspended": suspended,
            "health": state.health,
            "EI": state.EI,
            "E": state.E,
            "L": state.L,
            "mode": mode,
            "diag": state.last,
        }


__all__ = ["NaKController"]
