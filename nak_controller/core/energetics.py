from __future__ import annotations

from typing import Dict

import numpy as np

from .state import StrategyState, clip
from .params import NaKParams
from .metrics import pnl_norm


def update_load(st: StrategyState, p: NaKParams, obs: Dict[str, float], NA: float) -> float:
    n = max(0.0, obs.get("trades", 0.0))
    v_raw = clip(obs.get("local_vol", 0.0), 0.0, 1.0)
    # noradrenaline scales perceived volatility (less impact with high NA focus)
    v = v_raw * (1.0 - p.na_scale * NA)
    d = clip(obs.get("local_dd", 0.0), 0.0, 1.0)
    e = clip(obs.get("tech_errors", 0.0), 0.0, 1.0)
    l = clip(obs.get("latency", 0.0), 0.0, 1.0)
    s = clip(obs.get("slippage", 0.0), 0.0, 1.0)

    noise = np.random.normal(0.0, p.noise_sigma * max(1e-9, v_raw))
    L_next = st.L + p.w_n * n + p.w_v * v + p.w_d * d + p.w_e * e + p.w_l * l + p.w_s * s + noise
    st.L = clip(L_next, p.L_min, p.L_max)
    return st.L


def update_energy(st: StrategyState, p: NaKParams, obs: Dict[str, float], NA: float, DA: float, da_unexp: float) -> float:
    # pnl in fraction of equity per step; convert to [0,1] with 0.5 neutral
    p_sig = pnl_norm(obs.get("pnl", 0.0), scale=obs.get("pnl_scale", 0.01))
    n = clip(obs.get("trades", 0.0), 0.0, 1.0)
    v_raw = clip(obs.get("local_vol", 0.0), 0.0, 1.0)
    v = v_raw * (1.0 - p.na_scale * NA)
    g = clip(obs.get("glial_support", 0.0), 0.0, 1.0)

    # base energy update
    delta = p.a_p * p_sig - p.a_n * n - p.a_v * v + p.a_g * g

    # dopamine energy boost for positive unexpected reward
    if da_unexp > 0.0:
        delta += p.a_da * da_unexp

    E_next = st.E + delta

    # energy debt & recovery mechanics
    if E_next < 0.0:
        st.debt += -E_next
        E_next = 0.0
    else:
        # recover debt gradually
        st.debt = max(0.0, st.debt * 0.95 - 0.01)
        E_next += 0.05 * (1.0 - min(1.0, st.debt))

    st.E = clip(E_next, 0.0, p.E_max)
    return st.E


def compute_EI(st: StrategyState, p: NaKParams, obs: Dict[str, float]) -> float:
    e_part = st.E / max(1e-9, p.E_max)
    l_part = 1.0 - (st.L - p.L_min) / max(1e-9, (p.L_max - p.L_min))
    p_part = pnl_norm(obs.get("pnl", 0.0), scale=obs.get("pnl_scale", 0.01))
    EI = p.u_e * e_part + p.u_l * l_part + p.u_p * p_part
    st.EI = clip(EI, 0.0, 1.0)
    st.health = st.EI
    return st.EI
