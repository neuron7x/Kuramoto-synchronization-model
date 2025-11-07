from __future__ import annotations

from typing import Any, Dict, Mapping

import yaml  # type: ignore[import-untyped]

from ..core.state import StrategyState
from ..core.params import NaKParams
from ..core.energetics import update_load, update_energy, compute_EI
from ..control.pi import pi_control, rate_limit
from ..control.neuromods import (
    dopamine,
    noradrenaline,
    serotonin,
    acetylcholine,
    modulate_risk_da,
    modulate_activity_ach,
)
from ..control.global_mode import choose_mode, band_expand_for_mode


class NaKController:
    """
    Orchestrates per-strategy NaK loop + global neuromods/modes.
    Input obs for strategy i (per step):
      trades, pnl, local_vol, local_dd, tech_errors, latency, slippage, glial_support (opt)
    Global obs (same step):
      global_vol, portfolio_dd, exposure, unexpected_reward
    Returns per-strategy limits: risk_per_trade_factor, max_position_factor, cooldown_ms, is_suspended, health
    """

    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)["nak"]
        self.p = NaKParams(
            L_min=cfg["L_min"],
            L_max=cfg["L_max"],
            E_max=cfg["E_max"],
            EI_low=cfg["EI_low"],
            EI_high=cfg["EI_high"],
            EI_crit=cfg["EI_crit"],
            EI_hysteresis=cfg["EI_hysteresis"],
            I_max=cfg["I_max"],
            r_min=cfg["r_min"],
            r_max=cfg["r_max"],
            f_min=cfg["f_min"],
            f_max=cfg["f_max"],
            delta_r_limit=cfg["delta_r_limit"],
            w_n=cfg["w_n"],
            w_v=cfg["w_v"],
            w_d=cfg["w_d"],
            w_e=cfg["w_e"],
            w_l=cfg["w_l"],
            w_s=cfg["w_s"],
            a_p=cfg["a_p"],
            a_n=cfg["a_n"],
            a_v=cfg["a_v"],
            a_g=cfg["a_g"],
            a_da=cfg["a_da"],
            u_e=cfg["u_e"],
            u_l=cfg["u_l"],
            u_p=cfg["u_p"],
            Kp=cfg["Kp"],
            Ki=cfg["Ki"],
            beta_DA=cfg["beta_DA"],
            eta_ACh=cfg["eta_ACh"],
            da_gain=cfg["da_gain"],
            na_vol_gain=cfg["na_vol_gain"],
            na_scale=cfg["na_scale"],
            ht_dd_gain=cfg["ht_dd_gain"],
            vol_amber=cfg["vol_amber"],
            vol_red=cfg["vol_red"],
            dd_amber=cfg["dd_amber"],
            dd_red=cfg["dd_red"],
            risk_GREEN=cfg["risk_mult"]["GREEN"],
            risk_AMBER=cfg["risk_mult"]["AMBER"],
            risk_RED=cfg["risk_mult"]["RED"],
            act_GREEN=cfg["activity_mult"]["GREEN"],
            act_AMBER=cfg["activity_mult"]["AMBER"],
            act_RED=cfg["activity_mult"]["RED"],
            band_GREEN=cfg["band_expand"]["GREEN"],
            band_AMBER=cfg["band_expand"]["AMBER"],
            band_RED=cfg["band_expand"]["RED"],
            noise_sigma=cfg["noise_sigma"],
        )
        self.states: Dict[str, StrategyState] = {}

    def get_state(self, sid: str) -> StrategyState:
        if sid not in self.states:
            self.states[sid] = StrategyState()
        return self.states[sid]

    def step(
        self,
        sid: str,
        local_obs: Dict[str, float],
        global_obs: Dict[str, float],
        bases: Mapping[str, float | int],
    ) -> Dict[str, Any]:
        st = self.get_state(sid)
        p = self.p

        # --- Neuromodulators (global) ---
        unexp = float(global_obs.get("unexpected_reward", 0.0))
        DA = dopamine(unexp, p.beta_DA)
        NA = noradrenaline(global_obs.get("global_vol", 0.0), p.na_vol_gain)
        HT = serotonin(global_obs.get("portfolio_dd", 0.0), p.ht_dd_gain)
        ACh = acetylcholine(global_obs.get("exposure", 0.0), p.eta_ACh)

        # --- Energetics --- (apply NA scaling + DA energy boost)
        update_load(st, p, local_obs, NA=NA)
        update_energy(st, p, local_obs, NA=NA, DA=DA, da_unexp=unexp)
        compute_EI(st, p, local_obs)

        # --- Global mode & band expansion ---
        mode = choose_mode(
            global_vol=global_obs.get("global_vol", 0.0),
            portfolio_dd=global_obs.get("portfolio_dd", 0.0),
            vol_amber=p.vol_amber,
            vol_red=p.vol_red,
            dd_amber=p.dd_amber,
            dd_red=p.dd_red,
        )
        band_exp = band_expand_for_mode(mode, p.band_GREEN, p.band_AMBER, p.band_RED)

        # --- PI control (nonlinear) ---
        err, integ, r_tilde = pi_control(st, p, band_expand=band_exp)

        # --- Risk modulation by DA ---
        r_local = modulate_risk_da(r_tilde, DA, p.da_gain, p.r_min, p.r_max)

        # --- Global risk/activity multipliers ---
        risk_mult = dict(GREEN=p.risk_GREEN, AMBER=p.risk_AMBER, RED=p.risk_RED)[mode]
        act_mult = dict(GREEN=p.act_GREEN, AMBER=p.act_AMBER, RED=p.act_RED)[mode]

        r_after_mode = r_local * risk_mult
        activity = modulate_activity_ach(act_mult, ACh)

        # --- Rate limit risk change ---
        r_limited = rate_limit(
            prev=st.last_risk,
            target=r_after_mode,
            limit=p.delta_r_limit,
            lo=p.r_min,
            hi=p.r_max,
        )

        # --- Frequency & suspension with hysteresis ---
        EI_norm = st.EI
        f_freq = max(p.f_min, min(p.f_max, EI_norm * activity))
        cooldown_ms = int(max(1.0, bases["cooldown_ms_base"] / max(1e-9, f_freq)))

        unsuspend_threshold = p.EI_crit + p.EI_hysteresis
        if st.suspended:
            suspended = EI_norm < unsuspend_threshold or (risk_mult == 0.0)
        else:
            suspended = (EI_norm < p.EI_crit) or (risk_mult == 0.0)

        # --- Limits (max position mirrors risk) ---
        risk_factor = r_limited if not suspended else p.r_min
        maxpos_factor = risk_factor

        st.suspended = suspended
        st.last_risk = risk_factor
        st.last = {
            "err": err,
            "I": integ,
            "r_tilde": r_tilde,
            "r_local": r_local,
            "DA": DA,
            "NA": NA,
            "5HT": HT,
            "ACh": ACh,
            "mode": mode,
            "risk_mult": risk_mult,
            "activity": activity,
            "band_exp": band_exp,
            "f_freq": f_freq,
        }

        return {
            "strategy_id": sid,
            "risk_per_trade_factor": risk_factor,
            "max_position_factor": maxpos_factor,
            "cooldown_ms": cooldown_ms,
            "is_suspended": suspended,
            "health": st.health,
            "EI": st.EI,
            "E": st.E,
            "L": st.L,
            "mode": mode,
            "diag": st.last,
        }
