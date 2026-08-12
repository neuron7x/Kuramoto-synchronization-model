# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,arg-type"
"""Tests for value functions: P&L attribution + dislocation detection."""

from __future__ import annotations

from geosync.neuroeconomics.dislocation_detector import DislocationDetector
from geosync.neuroeconomics.pnl_attribution import PnLAttributor

# === P&L Attribution ===


def test_attribution_tracks_regime_pnl() -> None:
    attr = PnLAttributor()
    attr.record(regime="METASTABLE", decision="TRADE", pnl=0.01, size=0.8)
    attr.record(regime="METASTABLE", decision="TRADE", pnl=-0.005, size=0.8)
    attr.record(regime="CRITICAL", decision="ABORT", pnl=0.0, size=0.0, hypothetical_pnl=-0.05)

    r = attr.report()
    assert r.by_regime["METASTABLE"].count == 2
    assert r.by_regime["METASTABLE"].total_pnl == 0.005
    assert r.total_trades == 2
    assert r.total_aborts == 1


def test_attribution_protection_value() -> None:
    """ABORT that avoided a loss = positive protection value."""
    attr = PnLAttributor()
    # 3 ABORTs avoiding losses
    for _ in range(3):
        attr.record(
            regime="CRITICAL",
            decision="ABORT",
            pnl=0.0,
            size=0.0,
            hypothetical_pnl=-0.1,
        )
    r = attr.report()
    assert r.protection_value == 0.3  # saved $0.30
    assert r.abort_avoided_pnl == 0.3


def test_attribution_observe_missed_pnl() -> None:
    """OBSERVE tracks what we missed (could be gain or loss)."""
    attr = PnLAttributor()
    attr.record(
        regime="METASTABLE",
        decision="OBSERVE",
        pnl=0.0,
        size=0.0,
        hypothetical_pnl=0.05,
    )
    attr.record(
        regime="METASTABLE",
        decision="OBSERVE",
        pnl=0.0,
        size=0.0,
        hypothetical_pnl=-0.02,
    )
    r = attr.report()
    assert abs(r.observe_missed_pnl - 0.03) < 1e-6


def test_attribution_sharpe_per_regime() -> None:
    import numpy as np

    attr = PnLAttributor()
    rng = np.random.RandomState(42)
    for _ in range(50):
        attr.record(
            regime="METASTABLE",
            decision="TRADE",
            pnl=0.002 + rng.normal(0, 0.001),  # positive mean, nonzero variance
            size=1.0,
        )
    r = attr.report()
    assert r.by_regime["METASTABLE"].sharpe > 0


def test_attribution_summary_dict() -> None:
    attr = PnLAttributor()
    attr.record(regime="COHERENT", decision="TRADE", pnl=0.02, size=0.9)
    d = attr.summary_dict()
    assert "total_pnl" in d
    assert "protection_value" in d
    assert "pnl_coherent" in d
    assert "sharpe_coherent" in d


# === Dislocation Detector ===


def test_dislocation_stable_topology() -> None:
    """Stable κ, γ, R → no dislocation."""
    dd = DislocationDetector()
    for _ in range(10):
        state = dd.update(kappa=0.3, gamma=1.0, order_r=0.5)
    assert state.dislocation_score < 0.3
    assert not state.is_pre_dislocation


def test_dislocation_detects_kappa_collapse() -> None:
    """Falling κ = topology fragmenting → pre-dislocation."""
    dd = DislocationDetector()
    for i in range(15):
        kappa = 0.5 - i * 0.05  # κ falling from 0.5 to -0.2
        state = dd.update(kappa=kappa, gamma=1.0, order_r=0.5)
    assert state.kappa_velocity < 0
    assert state.dislocation_score > 0.0


def test_dislocation_detects_herding_onset() -> None:
    """R accelerating = everyone running same direction."""
    dd = DislocationDetector()
    for i in range(15):
        # Quadratic R: acceleration > 0
        r = 0.3 + 0.002 * i * i  # R = 0.3 + 0.002*i² (accelerating)
        state = dd.update(kappa=0.0, gamma=1.0, order_r=min(1.0, r))
    assert state.r_acceleration > 0


def test_dislocation_lead_time_nonzero_on_crisis() -> None:
    """When κ is falling fast, lead_bars > 0."""
    dd = DislocationDetector()
    for i in range(10):
        state = dd.update(kappa=0.5 - i * 0.1, gamma=1.0 + i * 0.05, order_r=0.5)
    assert state.lead_bars >= 3


def test_dislocation_nan_safe() -> None:
    dd = DislocationDetector()
    for _ in range(10):
        state = dd.update(kappa=float("nan"), gamma=float("inf"), order_r=float("-inf"))
    assert state.dislocation_score >= 0.0


def test_sharpe_degenerate_guard_returns_zero_not_a_division() -> None:
    """`if self.pnl_std < 1e-12: return 0.0` — zero-variance P&L has an UNDEFINED Sharpe.

    Every existing case has positive variance, so the guard's `Lt` was never pinned. Under
    `Lt -> GtE` it inverts: a normal-variance regime returns 0.0 (Sharpe silently erased) while
    a zero-variance regime divides by ~0. Both directions are pinned with a hand-built
    RegimeStats.
    """
    from geosync.neuroeconomics.pnl_attribution import RegimeStats

    # count>=2 and positive variance: avg=2, var = 24/4 - 4 = 2, std=sqrt(2) -> Sharpe != 0.
    normal = RegimeStats(count=4, total_pnl=8.0, sum_sq_pnl=24.0)
    assert normal.pnl_std > 1e-12
    assert normal.sharpe != 0.0, "a positive-variance regime must have a non-zero Sharpe"

    # count<2 -> pnl_std==0.0 -> the guard must return exactly 0.0, never divide.
    degenerate = RegimeStats(count=1, total_pnl=2.0, sum_sq_pnl=4.0)
    assert degenerate.pnl_std == 0.0
    assert degenerate.sharpe == 0.0


def test_avg_size_guards_against_empty_regime() -> None:
    """`total_size / count if count > 0 else 0.0` — an empty regime has no average size.

    Under `Gt -> LtE` the guard inverts: a populated regime returns 0.0 and an empty one
    divides by zero. Pinned in both directions.
    """
    from geosync.neuroeconomics.pnl_attribution import RegimeStats

    populated = RegimeStats(count=4, total_size=10.0)
    assert populated.avg_size == 2.5, "a populated regime must report its true average size"
    assert RegimeStats(count=0, total_size=10.0).avg_size == 0.0


def test_pre_dislocation_flag_requires_both_score_and_kappa_velocity() -> None:
    """`is_pre = score > 0.3 and kv < kappa_threshold` — degrading topology, price not yet moved.

    Nothing read the flag, so three mutants survived. A sharp topology break drives BOTH
    conditions true (flag True) and kills `Gt -> LtE` on the score and `Lt -> GtE` on kv; a
    milder break where the score stays below 0.3 but kv is well past the threshold leaves the
    flag False and kills `And -> Or` (under which one satisfied condition would wrongly raise
    it).
    """
    from geosync.neuroeconomics.dislocation_detector import DislocationDetector

    sharp = DislocationDetector()
    for _ in range(10):
        sharp.update(kappa=0.4, gamma=1.0, order_r=0.5)
    for i in range(4):
        s_true = sharp.update(
            kappa=0.4 - 0.3 * (i + 1),
            gamma=1.0 + 0.6 * (i + 1),
            order_r=min(1.0, 0.5 + 0.12 * (i + 1)),
        )
    assert s_true.dislocation_score > 0.3 and s_true.kappa_velocity < -0.05
    assert s_true.is_pre_dislocation is True

    mild = DislocationDetector()
    for _ in range(12):
        mild.update(kappa=0.4, gamma=1.0, order_r=0.5)
    for i in range(6):
        s_false = mild.update(
            kappa=0.4 - 0.15 * (i + 1),
            gamma=1.0 + 0.3 * (i + 1),
            order_r=min(1.0, 0.5 + 0.08 * (i + 1)),
        )
    # score below the 0.3 gate but kv past the threshold: exactly the (False, True) case.
    assert s_false.dislocation_score <= 0.3 and s_false.kappa_velocity < -0.05
    assert s_false.is_pre_dislocation is False, "one satisfied condition must not raise the flag"
