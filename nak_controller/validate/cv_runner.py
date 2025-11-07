"""Cross-validation harness for the NaK controller.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from typing import Dict, List, TypedDict

import numpy as np

from ..integration.hook import NaKHook
from ..risk.cvar import cvar_es
from .sim_env import multi_regime_stream


class StrategyBase(TypedDict):
    rpt: float
    maxpos: float
    cd_ms: int


def run_cv(
    config_path: str,
    steps: int = 1200,
    seeds: int = 8,
    n_strats: int = 3,
) -> Dict[str, Dict[str, float]]:
    results: Dict[str, List[Dict[str, float]]] = {"baseline": [], "nak": []}

    for s in range(seeds):
        hook = NaKHook(config_path, seed=2024 + s)
        bases: List[StrategyBase] = [
            {"rpt": 0.0020, "maxpos": 1.0, "cd_ms": 2000},
            {"rpt": 0.0015, "maxpos": 1.0, "cd_ms": 2200},
            {"rpt": 0.0010, "maxpos": 1.0, "cd_ms": 2500},
        ]
        equity_b = np.ones(n_strats)
        equity_n = np.ones(n_strats)
        ret_buf_b: List[float] = []
        ret_buf_n: List[float] = []
        susp_share = 0.0
        oob_share = 0.0
        steps_count = 0
        port_peak_n = 1.0
        peaks_n = [1.0] * n_strats

        for obs in multi_regime_stream(steps, seed=1234 + s * 7):
            steps_count += 1
            local_list: List[Dict[str, float]] = []
            for i in range(n_strats):
                jitter = (i - 1) * 0.0003
                pnl = obs["ret"] + jitter + 0.5 * obs["ret"] * np.sign(jitter)
                local = {
                    "trades": min(1.0, 0.5 + 5.0 * abs(obs["ret"])),
                    "pnl": pnl,
                    "pnl_scale": 0.01,
                    "local_vol": min(1.0, abs(obs["ret"]) * 25),
                    "local_dd": 0.0,
                    "tech_errors": 0.0,
                    "latency": min(1.0, 0.3 + abs(obs["ret"]) * 10),
                    "slippage": min(1.0, abs(obs["ret"]) * 5e-3),
                    "glial_support": 0.0,
                }
                local_list.append(local)

            r_b = 0.0
            for i in range(n_strats):
                ret_i = local_list[i]["pnl"] * bases[i]["rpt"]
                equity_b[i] *= 1.0 + ret_i
                r_b += ret_i
            r_b /= n_strats
            ret_buf_b.append(r_b)

            port_val_prev = float(np.mean(equity_n))
            port_peak_n = max(port_peak_n, port_val_prev)
            port_dd = 0.0 if port_peak_n == 0 else max(0.0, 1.0 - port_val_prev / port_peak_n)
            global_obs: Dict[str, float] = {
                "global_vol": obs["global_vol"],
                "portfolio_dd": port_dd,
                "exposure": 1.0,
                "unexpected_reward": 0.0,
            }
            r_n = 0.0
            susp_now = 0
            oob_now = 0
            for i in range(n_strats):
                peaks_n[i] = max(peaks_n[i], equity_n[i])
                local_list[i]["local_dd"] = (
                    0.0 if peaks_n[i] == 0 else max(0.0, 1.0 - equity_n[i] / peaks_n[i])
                )
                out = hook.compute_limits(
                    strategy_id=f"strat_{i}",
                    local_obs=local_list[i],
                    global_obs=global_obs,
                    risk_per_trade_base=bases[i]["rpt"],
                    max_position_base=bases[i]["maxpos"],
                    cooldown_ms_base=bases[i]["cd_ms"],
                )
                oob_now += int(out.EI < 0.35 or out.EI > 0.65)
                susp_now += int(out.is_suspended)
                ret_i = local_list[i]["pnl"] * out.risk_per_trade_factor
                equity_n[i] *= 1.0 + ret_i
                r_n += ret_i
            r_n /= n_strats
            ret_buf_n.append(r_n)
            susp_share += susp_now / n_strats
            oob_share += oob_now / n_strats

        arr_b = np.array(ret_buf_b, float)
        arr_n = np.array(ret_buf_n, float)
        std_b = float(np.std(arr_b))
        std_n = float(np.std(arr_n))
        mean_b = float(np.mean(arr_b))
        mean_n = float(np.mean(arr_n))
        cvar_b = cvar_es(arr_b, alpha=0.95)
        cvar_n = cvar_es(arr_n, alpha=0.95)
        results["baseline"].append({"mean": mean_b, "std": std_b, "cvar": cvar_b})
        results["nak"].append(
            {
                "mean": mean_n,
                "std": std_n,
                "cvar": cvar_n,
                "out_of_band": oob_share / steps_count,
                "suspended": susp_share / steps_count,
            }
        )

    def avg(ds: List[Dict[str, float]]) -> Dict[str, float]:
        keys = list(ds[0].keys())
        return {k: float(np.mean([d[k] for d in ds])) for k in keys}

    return {"baseline": avg(results["baseline"]), "nak": avg(results["nak"])}
