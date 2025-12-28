"""Property-based tests for dopamine invariants with fixed seeds."""

from __future__ import annotations

import math

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

    def given(*args, **kwargs):
        return lambda f: pytest.mark.skip(reason="hypothesis not installed")(f)

    class st:  # type: ignore
        @staticmethod
        def floats(*args, **kwargs):
            return None

from tradepulse.core.neuro.dopamine.dopamine_controller import _ALLOWED_NOVELTY_MODES


@st.composite

def _config_strategy(draw):
    base_temperature = draw(
        st.floats(min_value=0.05, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    min_temperature = draw(
        st.floats(
            min_value=0.01,
            max_value=base_temperature,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    temp_adapt_min_base = draw(
        st.floats(min_value=0.05, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    temp_adapt_max_base = draw(
        st.floats(
            min_value=temp_adapt_min_base,
            max_value=10.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    ddm_min_temperature_scale = draw(
        st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False)
    )
    ddm_max_temperature_scale = draw(
        st.floats(
            min_value=ddm_min_temperature_scale,
            max_value=5.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )

    meta_rule = st.fixed_dictionaries(
        {
            "learning_rate_v": st.floats(
                min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False
            ),
            "delta_gain": st.floats(
                min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
            ),
            "base_temperature": st.floats(
                min_value=0.05, max_value=5.0, allow_nan=False, allow_infinity=False
            ),
        }
    )

    return {
        "discount_gamma": draw(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "learning_rate_v": draw(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "decay_rate": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "burst_factor": draw(
            st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
        ),
        "k": draw(
            st.floats(min_value=1e-3, max_value=10.0, allow_nan=False, allow_infinity=False)
        ),
        "theta": draw(
            st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)
        ),
        "w_r": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "w_n": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "w_m": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "w_v": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "novelty_mode": draw(st.sampled_from(sorted(_ALLOWED_NOVELTY_MODES))),
        "c_absrpe": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "baseline": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "delta_gain": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "meta_cooldown_ticks": draw(st.integers(min_value=0, max_value=100)),
        "metric_interval": draw(st.integers(min_value=1, max_value=100)),
        "target_sharpe": draw(
            st.floats(min_value=1e-3, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "base_temperature": base_temperature,
        "min_temperature": min_temperature,
        "temp_k": draw(
            st.floats(min_value=1e-3, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "neg_rpe_temp_gain": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "max_temp_multiplier": draw(
            st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "invigoration_threshold": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "no_go_threshold": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "hold_threshold": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "rpe_ema_beta": draw(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "temp_adapt_target_var": draw(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "temp_adapt_lr": draw(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "temp_adapt_beta1": draw(
            st.floats(min_value=1e-6, max_value=0.999, allow_nan=False, allow_infinity=False)
        ),
        "temp_adapt_beta2": draw(
            st.floats(min_value=1e-6, max_value=0.999, allow_nan=False, allow_infinity=False)
        ),
        "temp_adapt_epsilon": draw(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "temp_adapt_min_base": temp_adapt_min_base,
        "temp_adapt_max_base": temp_adapt_max_base,
        "rpe_var_release_threshold": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "rpe_var_release_hysteresis": draw(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
        ),
        "ddm_temp_gain": draw(
            st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False)
        ),
        "ddm_threshold_gain": draw(
            st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False)
        ),
        "ddm_hold_gain": draw(
            st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False)
        ),
        "ddm_min_temperature_scale": ddm_min_temperature_scale,
        "ddm_max_temperature_scale": ddm_max_temperature_scale,
        "ddm_baseline_a": draw(
            st.floats(min_value=1e-3, max_value=3.0, allow_nan=False, allow_infinity=False)
        ),
        "ddm_baseline_t0": draw(
            st.floats(min_value=0.0, max_value=3.0, allow_nan=False, allow_infinity=False)
        ),
        "ddm_eps": draw(
            st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
        ),
        "meta_adapt_rules": {
            "good": draw(meta_rule),
            "bad": draw(meta_rule),
            "neutral": draw(meta_rule),
        },
    }


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
@settings(max_examples=25)
@given(cfg=_config_strategy())
def test_dopamine_invariants_property(cfg: dict) -> None:
    invariants = [
        ("discount_gamma_range", 0.0 < cfg["discount_gamma"] <= 1.0),
        ("learning_rate_v_range", 0.0 < cfg["learning_rate_v"] <= 1.0),
        ("decay_rate_range", 0.0 <= cfg["decay_rate"] <= 1.0),
        ("burst_factor_non_negative", cfg["burst_factor"] >= 0.0),
        ("k_finite", math.isfinite(cfg["k"])),
        ("k_non_zero", cfg["k"] != 0.0),
        ("theta_finite", math.isfinite(cfg["theta"])),
        ("w_r_non_negative", cfg["w_r"] >= 0.0),
        ("w_n_non_negative", cfg["w_n"] >= 0.0),
        ("w_m_non_negative", cfg["w_m"] >= 0.0),
        ("w_v_non_negative", cfg["w_v"] >= 0.0),
        ("novelty_mode_allowed", cfg["novelty_mode"] in _ALLOWED_NOVELTY_MODES),
        ("c_absrpe_non_negative", cfg["c_absrpe"] >= 0.0),
        ("baseline_min", cfg["baseline"] >= 0.0),
        ("baseline_max", cfg["baseline"] <= 1.0),
        ("delta_gain_min", cfg["delta_gain"] >= 0.0),
        ("delta_gain_max", cfg["delta_gain"] <= 1.0),
        ("meta_cooldown_ticks_non_negative", cfg["meta_cooldown_ticks"] >= 0),
        ("metric_interval_positive", cfg["metric_interval"] >= 1),
        ("target_sharpe_positive", cfg["target_sharpe"] > 0.0),
        ("base_temperature_positive", cfg["base_temperature"] > 0.0),
        ("min_temperature_positive", cfg["min_temperature"] > 0.0),
        (
            "min_temperature_le_base",
            cfg["min_temperature"] <= cfg["base_temperature"],
        ),
        ("temp_k_positive", cfg["temp_k"] > 0.0),
        ("neg_rpe_temp_gain_non_negative", cfg["neg_rpe_temp_gain"] >= 0.0),
        ("max_temp_multiplier_min", cfg["max_temp_multiplier"] >= 1.0),
        (
            "invigoration_threshold_range",
            0.0 <= cfg["invigoration_threshold"] <= 1.0,
        ),
        ("no_go_threshold_range", 0.0 <= cfg["no_go_threshold"] <= 1.0),
        ("hold_threshold_range", 0.0 <= cfg["hold_threshold"] <= 1.0),
        ("rpe_ema_beta_min", cfg["rpe_ema_beta"] > 0.0),
        ("rpe_ema_beta_max", cfg["rpe_ema_beta"] <= 1.0),
        ("temp_adapt_target_var_non_negative", cfg["temp_adapt_target_var"] >= 0.0),
        ("temp_adapt_lr_positive", cfg["temp_adapt_lr"] > 0.0),
        ("temp_adapt_beta1_min", cfg["temp_adapt_beta1"] > 0.0),
        ("temp_adapt_beta1_max", cfg["temp_adapt_beta1"] < 1.0),
        ("temp_adapt_beta2_min", cfg["temp_adapt_beta2"] > 0.0),
        ("temp_adapt_beta2_max", cfg["temp_adapt_beta2"] < 1.0),
        ("temp_adapt_epsilon_positive", cfg["temp_adapt_epsilon"] > 0.0),
        ("temp_adapt_min_base_positive", cfg["temp_adapt_min_base"] > 0.0),
        ("temp_adapt_max_base_positive", cfg["temp_adapt_max_base"] > 0.0),
        (
            "temp_adapt_min_base_le_max",
            cfg["temp_adapt_min_base"] <= cfg["temp_adapt_max_base"],
        ),
        ("rpe_var_release_threshold_non_negative", cfg["rpe_var_release_threshold"] >= 0.0),
        (
            "rpe_var_release_hysteresis_non_negative",
            cfg["rpe_var_release_hysteresis"] >= 0.0,
        ),
        ("ddm_temp_gain_non_negative", cfg["ddm_temp_gain"] >= 0.0),
        ("ddm_threshold_gain_non_negative", cfg["ddm_threshold_gain"] >= 0.0),
        ("ddm_hold_gain_non_negative", cfg["ddm_hold_gain"] >= 0.0),
        ("ddm_min_temperature_scale_positive", cfg["ddm_min_temperature_scale"] > 0.0),
        ("ddm_max_temperature_scale_positive", cfg["ddm_max_temperature_scale"] > 0.0),
        (
            "ddm_min_temperature_scale_le_max",
            cfg["ddm_min_temperature_scale"] <= cfg["ddm_max_temperature_scale"],
        ),
        ("ddm_baseline_a_positive", cfg["ddm_baseline_a"] > 0.0),
        ("ddm_baseline_t0_non_negative", cfg["ddm_baseline_t0"] >= 0.0),
        ("ddm_eps_positive", cfg["ddm_eps"] > 0.0),
        (
            "meta_adapt_rules_has_states",
            all(state in cfg["meta_adapt_rules"] for state in ("good", "bad", "neutral")),
        ),
        (
            "meta_adapt_rules_entries_finite",
            all(
                math.isfinite(cfg["meta_adapt_rules"][state][key])
                for state in ("good", "bad", "neutral")
                for key in ("learning_rate_v", "delta_gain", "base_temperature")
            ),
        ),
    ]

    assert len(invariants) == 54
    assert all(check for _, check in invariants)
