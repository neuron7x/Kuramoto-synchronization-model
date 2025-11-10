"""Property-based tests for NaK controller invariants.

These tests use fixed random seeds and bounded inputs to verify that
critical safety properties and mathematical invariants hold across
all reachable states.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from nak_controller.control.global_mode import choose_mode
from nak_controller.control.neuromods import (
    acetylcholine,
    dopamine,
    modulate_activity_ach,
    modulate_risk_da,
    noradrenaline,
    serotonin,
)
from nak_controller.control.pi import rate_limit
from nak_controller.core.state import clip
from nak_controller.runtime.controller import NaKController

CONFIG_PATH = Path("nak_controller/conf/nak.yaml")


class TestStateInvariants:
    """Test that state variables remain bounded under all conditions."""

    def test_energy_always_nonnegative(self) -> None:
        """Energy (E) must never go negative, even with severe losses."""
        controller = NaKController(CONFIG_PATH, seed=1)
        params = controller.params

        # Extreme loss scenario
        local_obs = {
            "trades": 1.0,
            "pnl": -0.1,  # Large loss
            "pnl_scale": 0.01,
            "local_vol": 1.0,
            "local_dd": 1.0,
            "tech_errors": 1.0,
            "latency": 1.0,
            "slippage": 0.01,
            "glial_support": 0.0,  # No support
        }
        global_obs = {
            "global_vol": 1.0,
            "portfolio_dd": 1.0,
            "exposure": 1.0,
            "unexpected_reward": -1.0,  # Negative surprise
        }
        bases = {"cooldown_ms_base": 1000.0}

        # Run 100 steps with extreme stress
        for _ in range(100):
            result = controller.step("stress", local_obs, global_obs, bases)
            assert result["E"] >= 0.0, "Energy went negative!"
            assert result["E"] <= params.E_max, "Energy exceeded E_max!"

    def test_load_bounded(self) -> None:
        """Load (L) must remain in [L_min, L_max] under all conditions."""
        controller = NaKController(CONFIG_PATH, seed=2)
        params = controller.params

        # High activity scenario
        local_obs = {
            "trades": 1.0,
            "pnl": 0.0,
            "pnl_scale": 0.01,
            "local_vol": 1.0,
            "local_dd": 1.0,
            "tech_errors": 1.0,
            "latency": 1.0,
            "slippage": 0.01,
            "glial_support": 0.0,
        }
        global_obs = {
            "global_vol": 0.5,
            "portfolio_dd": 0.3,
            "exposure": 0.5,
            "unexpected_reward": 0.0,
        }
        bases = {"cooldown_ms_base": 1000.0}

        for _ in range(100):
            result = controller.step("load_test", local_obs, global_obs, bases)
            assert result["L"] >= params.L_min, "Load below L_min!"
            assert result["L"] <= params.L_max, "Load above L_max!"

    def test_ei_bounded(self) -> None:
        """Engagement Index (EI) must remain in [0, 1]."""
        controller = NaKController(CONFIG_PATH, seed=3)
        rng = np.random.default_rng(42)

        for _ in range(50):
            # Random observations
            local_obs = {
                "trades": float(rng.uniform(0, 1)),
                "pnl": float(rng.normal(0, 0.01)),
                "pnl_scale": 0.01,
                "local_vol": float(rng.uniform(0, 1)),
                "local_dd": float(rng.uniform(0, 1)),
                "tech_errors": float(rng.uniform(0, 0.2)),
                "latency": float(rng.uniform(0, 0.5)),
                "slippage": float(rng.uniform(0, 0.002)),
                "glial_support": float(rng.uniform(0, 1)),
            }
            global_obs = {
                "global_vol": float(rng.uniform(0, 1)),
                "portfolio_dd": float(rng.uniform(0, 1)),
                "exposure": float(rng.uniform(-1, 1)),
                "unexpected_reward": float(rng.normal(0, 0.1)),
            }
            bases = {"cooldown_ms_base": 2000.0}

            result = controller.step("ei_test", local_obs, global_obs, bases)
            assert 0.0 <= result["EI"] <= 1.0, f"EI out of bounds: {result['EI']}"


class TestOutputInvariants:
    """Test that control outputs remain within specified bounds."""

    def test_risk_factor_bounded(self) -> None:
        """risk_per_trade_factor must stay in [r_min, r_max]."""
        controller = NaKController(CONFIG_PATH, seed=4)
        params = controller.params
        rng = np.random.default_rng(44)

        for _ in range(50):
            local_obs = {
                "trades": float(rng.uniform(0, 1)),
                "pnl": float(rng.normal(0, 0.005)),
                "pnl_scale": 0.01,
                "local_vol": float(rng.uniform(0, 1)),
                "local_dd": float(rng.uniform(0, 1)),
                "tech_errors": float(rng.uniform(0, 0.1)),
                "latency": float(rng.uniform(0, 0.3)),
                "slippage": float(rng.uniform(0, 0.001)),
                "glial_support": float(rng.uniform(0, 1)),
            }
            global_obs = {
                "global_vol": float(rng.uniform(0, 0.8)),
                "portfolio_dd": float(rng.uniform(0, 0.6)),
                "exposure": float(rng.uniform(0, 1)),
                "unexpected_reward": float(rng.normal(0, 0.05)),
            }
            bases = {"cooldown_ms_base": 1500.0}

            result = controller.step("risk_test", local_obs, global_obs, bases)
            risk = result["risk_per_trade_factor"]
            assert params.r_min <= risk <= params.r_max, f"Risk out of bounds: {risk}"

    def test_cooldown_positive(self) -> None:
        """cooldown_ms must be at least 1 millisecond."""
        controller = NaKController(CONFIG_PATH, seed=5)

        local_obs = {
            "trades": 0.1,
            "pnl": 0.005,
            "pnl_scale": 0.01,
            "local_vol": 0.2,
            "local_dd": 0.1,
            "tech_errors": 0.0,
            "latency": 0.0,
            "slippage": 0.0,
            "glial_support": 1.0,  # Max support
        }
        global_obs = {
            "global_vol": 0.1,
            "portfolio_dd": 0.05,
            "exposure": 0.3,
            "unexpected_reward": 0.05,
        }

        # Try with very small base cooldown
        bases = {"cooldown_ms_base": 10.0}

        for _ in range(20):
            result = controller.step("cooldown_test", local_obs, global_obs, bases)
            assert result["cooldown_ms"] >= 1, "Cooldown below 1 ms!"


class TestMonotonicityProperties:
    """Test monotonicity and consistency properties."""

    def test_higher_ei_enables_unsuspension(self) -> None:
        """When EI recovers above threshold, suspension should lift."""
        controller = NaKController(CONFIG_PATH, seed=6)
        params = controller.params

        # Force suspension with bad conditions
        bad_local = {
            "trades": 1.0,
            "pnl": -0.02,
            "pnl_scale": 0.01,
            "local_vol": 1.0,
            "local_dd": 1.0,
            "tech_errors": 0.5,
            "latency": 0.8,
            "slippage": 0.01,
            "glial_support": 0.0,
        }
        bad_global = {
            "global_vol": 0.95,
            "portfolio_dd": 0.85,
            "exposure": 0.9,
            "unexpected_reward": -0.2,
        }
        bases = {"cooldown_ms_base": 2000.0}

        # Run until suspended
        for _ in range(20):
            result = controller.step("mono_test", bad_local, bad_global, bases)
            if result["is_suspended"]:
                break

        assert result["is_suspended"], "Failed to suspend under stress"

        # Now improve conditions drastically
        good_local = {
            "trades": 0.1,
            "pnl": 0.01,
            "pnl_scale": 0.01,
            "local_vol": 0.1,
            "local_dd": 0.0,
            "tech_errors": 0.0,
            "latency": 0.0,
            "slippage": 0.0,
            "glial_support": 1.0,
        }
        good_global = {
            "global_vol": 0.1,
            "portfolio_dd": 0.05,
            "exposure": 0.2,
            "unexpected_reward": 0.2,
        }

        # Run until unsuspended
        unsuspended = False
        for _ in range(100):
            result = controller.step("mono_test", good_local, good_global, bases)
            if not result["is_suspended"]:
                unsuspended = True
                # Verify EI is above threshold
                ei = result["EI"]
                assert ei >= params.EI_crit + params.EI_hysteresis, (
                    f"Unsuspended but EI={ei:.3f} < "
                    f"{params.EI_crit + params.EI_hysteresis:.3f}"
                )
                break

        assert unsuspended, "Failed to unsuspend after recovery"


class TestNeuromodulatorProperties:
    """Test properties of neuromodulator functions."""

    def test_dopamine_range(self) -> None:
        """Dopamine output must be in [0, 1] for any input."""
        for unexp in [-10.0, -1.0, 0.0, 0.5, 1.0, 10.0]:
            da = dopamine(unexp, beta_DA=0.8)
            assert 0.0 <= da <= 1.0, f"DA out of range for unexp={unexp}: {da}"

    def test_noradrenaline_range(self) -> None:
        """Noradrenaline output must be in [0, 1] for any input."""
        for vol in [0.0, 0.5, 1.0, 2.0, 10.0]:
            na = noradrenaline(vol, na_vol_gain=1.0)
            assert 0.0 <= na <= 1.0, f"NA out of range for vol={vol}: {na}"

    def test_serotonin_range(self) -> None:
        """Serotonin output must be in [0, 1] for any input."""
        for dd in [0.0, 0.5, 1.0, 2.0]:
            ht = serotonin(dd, ht_dd_gain=1.0)
            assert 0.0 <= ht <= 1.0, f"5HT out of range for dd={dd}: {ht}"

    def test_acetylcholine_range(self) -> None:
        """Acetylcholine output must be in [0, 1] for any input."""
        for exp in [-2.0, -1.0, 0.0, 0.5, 1.0, 2.0]:
            ach = acetylcholine(exp, eta_ACh=0.6)
            assert 0.0 <= ach <= 1.0, f"ACh out of range for exp={exp}: {ach}"


class TestGlobalModeConsistency:
    """Test that global mode selection is consistent."""

    def test_red_mode_triggers_suspension(self) -> None:
        """RED mode must always result in suspension."""
        controller = NaKController(CONFIG_PATH, seed=7)

        # Force RED mode with extreme conditions
        local_obs = {
            "trades": 0.5,
            "pnl": 0.005,  # Even with profit
            "pnl_scale": 0.01,
            "local_vol": 0.3,
            "local_dd": 0.2,
            "tech_errors": 0.0,
            "latency": 0.0,
            "slippage": 0.0,
            "glial_support": 0.8,  # Good local conditions
        }
        red_global = {
            "global_vol": 0.95,  # Exceeds vol_red threshold
            "portfolio_dd": 0.85,  # Exceeds dd_red threshold
            "exposure": 0.5,
            "unexpected_reward": 0.0,
        }
        bases = {"cooldown_ms_base": 2000.0}

        result = controller.step("red_test", local_obs, red_global, bases)
        assert result["mode"] == "RED", "Failed to trigger RED mode"
        assert result["is_suspended"], "RED mode did not suspend strategy"

    def test_mode_ordering(self) -> None:
        """Mode should escalate with increasing stress."""
        # GREEN conditions
        assert choose_mode(0.5, 0.2, vol_amber=0.7, vol_red=0.9, dd_amber=0.4, dd_red=0.7) == "GREEN"

        # AMBER volatility
        assert choose_mode(0.75, 0.2, vol_amber=0.7, vol_red=0.9, dd_amber=0.4, dd_red=0.7) == "AMBER"

        # AMBER drawdown
        assert choose_mode(0.5, 0.5, vol_amber=0.7, vol_red=0.9, dd_amber=0.4, dd_red=0.7) == "AMBER"

        # RED volatility
        assert choose_mode(0.95, 0.3, vol_amber=0.7, vol_red=0.9, dd_amber=0.4, dd_red=0.7) == "RED"

        # RED drawdown
        assert choose_mode(0.5, 0.8, vol_amber=0.7, vol_red=0.9, dd_amber=0.4, dd_red=0.7) == "RED"


class TestRateLimiting:
    """Test that rate limiting prevents abrupt changes."""

    def test_rate_limit_respects_delta_max(self) -> None:
        """Rate limiter must not allow changes exceeding delta_max."""
        prev = 1.0
        target = 1.5
        limit = 0.1

        result = rate_limit(prev, target, limit=limit, lo=0.0, hi=2.0)
        assert abs(result - prev) <= limit + 1e-6, "Rate limit violated!"

        # Downward
        result_down = rate_limit(prev, 0.5, limit=limit, lo=0.0, hi=2.0)
        assert abs(result_down - prev) <= limit + 1e-6, "Downward rate limit violated!"

    def test_rate_limit_gradual_convergence(self) -> None:
        """Multiple rate-limited steps should gradually reach target."""
        prev = 1.0
        target = 1.6
        limit = 0.1
        steps_needed = int(np.ceil(abs(target - prev) / limit))

        current = prev
        for _ in range(steps_needed):
            current = rate_limit(current, target, limit=limit, lo=0.0, hi=2.0)

        assert abs(current - target) < limit, "Failed to converge to target"


class TestClipFunction:
    """Test the basic clip utility."""

    def test_clip_bounds(self) -> None:
        """clip() must return value in [lo, hi]."""
        assert clip(0.5, 0.0, 1.0) == 0.5
        assert clip(-0.5, 0.0, 1.0) == 0.0
        assert clip(1.5, 0.0, 1.0) == 1.0
        assert clip(100.0, 0.0, 1.0) == 1.0
        assert clip(-100.0, 0.0, 1.0) == 0.0


class TestDopamineModulation:
    """Test DA modulation of risk."""

    def test_da_modulation_bounded(self) -> None:
        """DA-modulated risk must remain in [r_min, r_max]."""
        for da in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for rate in [0.5, 1.0, 1.5]:
                result = modulate_risk_da(
                    rate, da, da_gain=0.25, r_min=0.2, r_max=1.8
                )
                assert 0.2 <= result <= 1.8, f"DA modulation out of bounds: {result}"


class TestActivityModulation:
    """Test ACh modulation of activity."""

    def test_ach_modulation_bounded(self) -> None:
        """ACh-modulated activity must remain in [0.25, 1.5]."""
        for ach in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for base in [0.6, 0.9, 1.2]:
                result = modulate_activity_ach(base, ach)
                assert 0.25 <= result <= 1.5, f"ACh modulation out of bounds: {result}"
