"""Runtime orchestration for the NaK controller."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Mapping

import numpy as np
import yaml

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
from ..core.config import NakConfig
from ..core.energetics import compute_EI, update_energy, update_load
from ..core.params import NaKParams
from ..core.state import StrategyState


class NaKController:
    """Stateful neuro-energetic controller managing per-strategy limits."""

    def __init__(
        self,
        config_path: str | Path,
        *,
        seed: int | None = None,
    ) -> None:
        config_path = Path(config_path)
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if "nak" not in raw:
            raise KeyError("configuration file must contain a 'nak' root key")
        cfg = NakConfig(**raw["nak"])
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
        resolved_seed = seed
        if resolved_seed is None:
            env_seed = os.getenv("NAK_SEED")
            if env_seed is not None:
                env_seed = env_seed.strip()
                if env_seed:
                    try:
                        resolved_seed = int(env_seed)
                    except ValueError as exc:
                        raise ValueError("NAK_SEED must be an integer") from exc
        self._seed = resolved_seed
        self._rng = np.random.default_rng(self._seed)
        self._states: Dict[str, StrategyState] = {}
        self._logger = logging.getLogger("runtime.telemetry.nak")

    @property
    def states(self) -> Mapping[str, StrategyState]:
        """Return a read-only view of registered states."""
        return self._states

    def export_tacl_metrics(self, strategy_id: str) -> Dict[str, float]:
        """Export TACL-compatible metrics for external monitoring.

        Returns a dictionary of all controller state variables and derived
        metrics suitable for time-series storage, dashboards, and alerts.

        **Exported Metrics:**
            - Energy, Load, Engagement Index (core metabolic state)
            - PI integrator, last error (control state)
            - Neuromodulator levels (DA, NA, 5-HT, ACh)
            - Risk factor, frequency, cooldown (output signals)
            - Suspension flag, mode, debt (state flags)

        Args:
            strategy_id: Strategy identifier to export metrics for.

        Returns:
            Dictionary of metric name → float value. Returns empty dict
            if strategy_id has never been stepped.

        Raises:
            KeyError: If strategy_id is not found in registered states.
        """
        if strategy_id not in self._states:
            return {}

        state = self._states[strategy_id]
        last = state.last

        return {
            # Core metabolic state
            "tacl.nak.energy": state.E,
            "tacl.nak.load": state.L,
            "tacl.nak.engagement_index": state.EI,
            "tacl.nak.debt": state.debt,
            # Control state
            "tacl.nak.integrator": state.I,
            "tacl.nak.pi_error": float(last.get("err", 0.0)),
            "tacl.nak.rate_raw": float(last.get("r_tilde", 1.0)),
            "tacl.nak.rate_modulated": float(last.get("r_local", 1.0)),
            "tacl.nak.rate_final": state.last_risk,
            # Neuromodulators
            "tacl.nak.dopamine": float(last.get("DA", 0.5)),
            "tacl.nak.noradrenaline": float(last.get("NA", 0.0)),
            "tacl.nak.serotonin": float(last.get("5HT", 0.0)),
            "tacl.nak.acetylcholine": float(last.get("ACh", 0.5)),
            # Global mode and multipliers
            "tacl.nak.risk_multiplier": float(last.get("risk_mult", 1.0)),
            "tacl.nak.activity_multiplier": float(last.get("activity", 1.0)),
            "tacl.nak.band_expansion": float(last.get("band_exp", 1.0)),
            # Output signals
            "tacl.nak.frequency": float(last.get("f_freq", 1.0)),
            # State flags
            "tacl.nak.suspended": float(state.suspended),
        }

    def reset(self, *, seed: int | None = None) -> None:
        """Clear all strategy state and optionally reseed randomness."""
        if seed is not None:
            self._seed = seed
        if self._seed is not None:
            self._rng = np.random.default_rng(self._seed)
        else:
            self._rng = np.random.default_rng()
        self._states.clear()

    def _get_state(self, strategy_id: str) -> StrategyState:
        if strategy_id not in self._states:
            self._states[strategy_id] = StrategyState()
        return self._states[strategy_id]

    def step(
        self,
        strategy_id: str,
        local_obs: Mapping[str, float],
        global_obs: Mapping[str, float],
        bases: Mapping[str, float],
    ) -> Dict[str, object]:
        """Advance the controller by one step and return limit factors."""
        state = self._get_state(strategy_id)
        params = self.params

        local = dict(local_obs)
        global_view = dict(global_obs)

        unexpected_reward = float(global_view.get("unexpected_reward", 0.0))
        DA = dopamine(unexpected_reward, params.beta_DA)
        NA = noradrenaline(
            float(global_view.get("global_vol", 0.0)), params.na_vol_gain
        )
        HT = serotonin(float(global_view.get("portfolio_dd", 0.0)), params.ht_dd_gain)
        ACh = acetylcholine(float(global_view.get("exposure", 0.0)), params.eta_ACh)

        update_load(state, params, local, NA, rng=self._rng)
        update_energy(state, params, local, NA=NA, DA=DA, da_unexp=unexpected_reward)
        compute_EI(state, params, local)

        mode = choose_mode(
            float(global_view.get("global_vol", 0.0)),
            float(global_view.get("portfolio_dd", 0.0)),
            vol_amber=params.vol_amber,
            vol_red=params.vol_red,
            dd_amber=params.dd_amber,
            dd_red=params.dd_red,
        )
        band_expansion = band_expand_for_mode(
            mode,
            band_GREEN=params.band_GREEN,
            band_AMBER=params.band_AMBER,
            band_RED=params.band_RED,
        )
        error, integrator, rate_raw = pi_control(
            state, params, band_expand=band_expansion
        )

        rate_local = modulate_risk_da(
            rate_raw, DA, params.da_gain, r_min=params.r_min, r_max=params.r_max
        )
        risk_multiplier = {
            "GREEN": params.risk_GREEN,
            "AMBER": params.risk_AMBER,
            "RED": params.risk_RED,
        }[mode]
        activity_multiplier = {
            "GREEN": params.act_GREEN,
            "AMBER": params.act_AMBER,
            "RED": params.act_RED,
        }[mode]

        rate_after_mode = rate_local * risk_multiplier
        limited_rate = rate_limit(
            state.last_risk,
            rate_after_mode,
            limit=params.delta_r_limit,
            lo=params.r_min,
            hi=params.r_max,
        )

        activity = modulate_activity_ach(activity_multiplier, ACh)

        engagement = state.EI
        freq = max(params.f_min, min(params.f_max, engagement * activity))
        base_cooldown = float(bases.get("cooldown_ms_base", 1000.0))
        cooldown_ms = int(max(1.0, base_cooldown / max(1e-9, freq)))

        unsuspend_threshold = params.EI_crit + params.EI_hysteresis
        if state.suspended:
            suspended = engagement < unsuspend_threshold or risk_multiplier == 0.0
        else:
            suspended = engagement < params.EI_crit or risk_multiplier == 0.0

        risk_factor = limited_rate if not suspended else params.r_min
        max_position_factor = risk_factor

        if not params.r_min <= risk_factor <= params.r_max:
            raise RuntimeError(
                f"risk_factor {risk_factor:.4f} outside bounds [{params.r_min}, {params.r_max}]"
            )
        if abs(max_position_factor - risk_factor) > 1e-6:  # pragma: no cover
            raise RuntimeError(
                "max_position_factor must equal risk_factor for deterministic sizing"
            )
        if mode == "RED" and not suspended:
            raise RuntimeError("RED mode must result in suspension")
        if cooldown_ms < 1:  # pragma: no cover
            raise RuntimeError("cooldown must be at least 1 ms")

        state.suspended = suspended
        state.last_risk = risk_factor
        state.last = {
            "err": error,
            "I": integrator,
            "r_tilde": rate_raw,
            "r_local": rate_local,
            "DA": DA,
            "NA": NA,
            "5HT": HT,
            "ACh": ACh,
            "mode": mode,
            "risk_mult": risk_multiplier,
            "activity": activity,
            "band_exp": band_expansion,
            "f_freq": freq,
        }

        # Export comprehensive TACL metrics for observability
        if self._logger.isEnabledFor(logging.INFO):
            self._logger.info(
                "nak.step",
                extra={
                    "event": "nak.step",
                    "strategy": strategy_id,
                    # Core metabolic state
                    "tacl.nak.energy": state.E,
                    "tacl.nak.load": state.L,
                    "tacl.nak.engagement_index": state.EI,
                    "tacl.nak.debt": state.debt,
                    # Control state
                    "tacl.nak.integrator": state.I,
                    "tacl.nak.pi_error": error,
                    "tacl.nak.rate_raw": rate_raw,
                    "tacl.nak.rate_modulated": rate_local,
                    "tacl.nak.rate_final": risk_factor,
                    # Neuromodulators
                    "tacl.nak.dopamine": DA,
                    "tacl.nak.noradrenaline": NA,
                    "tacl.nak.serotonin": HT,
                    "tacl.nak.acetylcholine": ACh,
                    # Global mode and multipliers
                    "tacl.nak.mode": mode,
                    "tacl.nak.risk_multiplier": risk_multiplier,
                    "tacl.nak.activity_multiplier": activity,
                    "tacl.nak.band_expansion": band_expansion,
                    # Output signals
                    "tacl.nak.risk_factor": risk_factor,
                    "tacl.nak.frequency": freq,
                    "tacl.nak.cooldown_ms": cooldown_ms,
                    "tacl.nak.suspended": suspended,
                    # State transitions
                    "tacl.nak.suspension_change": suspended != state.suspended,
                },
            )

        result: Dict[str, object] = {
            "strategy_id": strategy_id,
            "risk_per_trade_factor": risk_factor,
            "max_position_factor": max_position_factor,
            "cooldown_ms": cooldown_ms,
            "is_suspended": suspended,
            "health": state.health,
            "EI": state.EI,
            "E": state.E,
            "L": state.L,
            "mode": mode,
            "diag": state.last,
        }
        return result


__all__ = ["NaKController"]
