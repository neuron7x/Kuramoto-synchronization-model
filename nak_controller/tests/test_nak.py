"""Unit tests covering key controller invariants."""
from __future__ import annotations

from typing import Any, Dict, cast

from nak_controller.integration.hook import NaKHook

CFG = "nak_controller/conf/nak.yaml"


def make_hook() -> NaKHook:
    return NaKHook(CFG)


def step(hook: NaKHook, **kwargs: float) -> Dict[str, Any]:
    local = dict(
        trades=kwargs.get("trades", 0.6),
        pnl=kwargs.get("pnl", 0.001),
        pnl_scale=0.01,
        local_vol=kwargs.get("local_vol", 0.3),
        local_dd=kwargs.get("local_dd", 0.1),
        tech_errors=kwargs.get("tech_errors", 0.0),
        latency=kwargs.get("latency", 0.3),
        slippage=kwargs.get("slippage", 0.0005),
        glial_support=kwargs.get("glial_support", 0.0),
    )
    global_obs = dict(
        global_vol=kwargs.get("global_vol", 0.3),
        portfolio_dd=kwargs.get("portfolio_dd", 0.1),
        exposure=kwargs.get("exposure", 1.0),
        unexpected_reward=kwargs.get("unexpected_reward", 0.0),
    )
    return hook.compute_limits(
        "s1",
        local,
        global_obs,
        base_risk_per_trade=0.002,
        base_max_position=1.0,
        base_cooldown_ms=2000,
    )


def test_bounds_and_invariants() -> None:
    hook = make_hook()
    out = step(hook)
    ei = cast(float, out["EI"])
    risk_factor = cast(float, out["risk_per_trade_factor"])
    maxpos_factor = cast(float, out["max_position_factor"])
    cooldown = cast(int, out["cooldown_ms"])
    assert 0.0 <= ei <= 1.0
    assert 0.2 <= risk_factor <= 1.8
    assert maxpos_factor == risk_factor
    assert cooldown >= 1


def test_modes_and_hysteresis() -> None:
    hook = make_hook()
    out_red = step(
        hook,
        global_vol=0.95,
        portfolio_dd=0.75,
        pnl=-0.002,
        trades=0.9,
        local_vol=0.95,
    )
    assert bool(out_red["is_suspended"]) or cast(str, out_red["mode"]) == "RED"
    out_rec = out_red
    for _ in range(6):
        out_rec = step(
            hook,
            global_vol=0.2,
            portfolio_dd=0.02,
            pnl=0.003,
            trades=0.2,
            local_vol=0.1,
        )
    assert cast(float, out_rec["EI"]) >= 0.15


def test_rate_limit() -> None:
    hook = make_hook()
    out1 = step(hook, pnl=0.005)
    out2 = step(hook, pnl=0.005, trades=0.0)
    r1 = cast(float, out1["risk_per_trade_factor"])
    r2 = cast(float, out2["risk_per_trade_factor"])
    assert abs(r2 - r1) <= 0.20 + 1e-6


def test_frequency_logic() -> None:
    hook = make_hook()
    o1 = step(hook, global_vol=0.3, local_vol=0.2)
    o2 = step(hook, global_vol=0.8, local_vol=0.8)
    assert cast(int, o1["cooldown_ms"]) != cast(int, o2["cooldown_ms"])
