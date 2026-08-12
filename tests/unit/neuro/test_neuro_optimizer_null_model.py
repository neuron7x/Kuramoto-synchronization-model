# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Null-model witness for the cross-neuromodulator balance optimizer.

Ledger
------
id: neuro-optimizer-balance-metrics (PARTIAL -> remediation ADD_NULL_MODEL).
Source: ``src/geosync/core/neuro/neuro_optimizer.py``.

Mechanism (what is actually computed)
-------------------------------------
``NeuroOptimizer._calculate_balance_metrics`` maps a neuromodulator *state*
to a scalar ``overall_balance_score`` in ``[0, 1]`` via::

    da_5ht_dev = |ratio - 1.67| / 1.67          # ratio = da / (sero + eps)
    ei_dev     = |E/I  - 1.5|  / 1.5            # E/I  = (da+arousal)/(gaba+sero)
    homeostatic_deviation = (da_5ht_dev + ei_dev) / 2
    overall_balance_score = 1 / (1 + homeostatic_deviation)

The score is therefore a deterministic, monotone-decreasing function of the
distance of the state's two arithmetic ratios from two hardcoded setpoints
(``da_5ht_ratio = 1.67``, ``excitation_inhibition = 1.5``). A state placed
exactly on both setpoints scores ~1.0; an arbitrary state scores lower.

Validity (what these tests establish)
-------------------------------------
* A configured / setpoint-aligned state scores above a threshold ``T`` that a
  *random* (null) state distribution fails to reach on average -> the scoring
  carries signal over chance, it is not vacuously high for any input.
* The DA/5-HT and E/I "ranges" are arithmetic engineering bounds: the config
  accepts arbitrary positive reals (e.g. ``(1e-9, 1e9)``) with no
  physiological-range gate, and the ratios pass through essentially unclipped.

Falsifier (ledger)
------------------
"Hardcoded ranges have no neuroscience citation; null-model needed (random
params should produce score below threshold by construction)." These tests
fail if (a) the random null can match the configured optimum on average, or
(b) the module begins to assert a biological / physiological range without a
cited source.

NON-CLAIM
---------
DA/5-HT and E/I are *engineering ratios*, NOT biological measurements. No
physiological-range claim is made or tested. All inputs are synthetic; nothing
here is calibrated to, or validated against, any neuroscience dataset.
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from geosync.core.neuro.neuro_optimizer import (
    NeuroOptimizer,
    NumericConfig,
    OptimizationConfig,
)

# --- Deterministic experiment constants (no magic numbers) -------------------

# Fixed seed so the null draw is reproducible bit-for-bit. Date-derived only to
# be memorable; the assertions below do not depend on its specific value beyond
# determinism (verified empirically: the null mean is ~2.7 std below T).
_NULL_SEED = 20260623

# Sample size for the null distribution. Large enough that the sample mean of
# the bounded ([0,1]) score concentrates tightly: the standard error of the
# mean is std/sqrt(N) ~= 0.081/sqrt(3000) ~= 1.5e-3, i.e. negligible vs the
# ~0.22 gap between the null mean and the threshold.
_NULL_SAMPLES = 3000

# Decision threshold T for "configured beats chance". Chosen strictly between
# the configured-optimum score (~0.999) and the null p99 (~0.924) measured for
# this seed, so the test is a real discriminator, not a tautology.
_BALANCE_THRESHOLD = 0.95

# Setpoint-aligned ("configured optimum") state. Derived analytically so both
# ratios sit on the optimizer's own setpoints:
#   ratio = da/sero = 0.5/0.3 = 1.667 == da_5ht setpoint (1.67)
#   E/I = (da+arousal)/(gaba+sero) = (0.5+0.55)/(0.4+0.3) = 1.5 == E/I setpoint
# arousal == attention -> arousal-attention coherence == 1.0.
_OPTIMUM_STATE: Dict[str, float] = {
    "dopamine_level": 0.5,
    "serotonin_level": 0.3,
    "gaba_inhibition": 0.4,
    "na_arousal": 0.55,
    "ach_attention": 0.55,
}

# Uniform null support per state variable. Bounds are the natural [near-0, 1]
# activation range for levels/attention and [near-0, 2] for arousal (matching
# the module's neutral arousal setpoint of 1.0 at mid-range). Lower bound is a
# small positive epsilon to keep ratios finite, not a biological claim.
_NULL_LEVEL_LOW = 0.01
_NULL_LEVEL_HIGH = 1.0
_NULL_AROUSAL_HIGH = 2.0


def _default_optimizer() -> NeuroOptimizer:
    return NeuroOptimizer(OptimizationConfig())


def _draw_null_state(rng: np.random.Generator) -> Dict[str, float]:
    """Sample one synthetic neuromodulator state from the uniform null."""
    return {
        "dopamine_level": float(rng.uniform(_NULL_LEVEL_LOW, _NULL_LEVEL_HIGH)),
        "serotonin_level": float(rng.uniform(_NULL_LEVEL_LOW, _NULL_LEVEL_HIGH)),
        "gaba_inhibition": float(rng.uniform(_NULL_LEVEL_LOW, _NULL_LEVEL_HIGH)),
        "na_arousal": float(rng.uniform(_NULL_LEVEL_LOW, _NULL_AROUSAL_HIGH)),
        "ach_attention": float(rng.uniform(_NULL_LEVEL_LOW, _NULL_LEVEL_HIGH)),
    }


def _null_scores() -> np.ndarray:
    """Deterministic array of balance scores under the random null model."""
    rng = np.random.default_rng(_NULL_SEED)
    optimizer = _default_optimizer()
    scores = np.empty(_NULL_SAMPLES, dtype=np.float64)
    for i in range(_NULL_SAMPLES):
        metrics = optimizer._calculate_balance_metrics(_draw_null_state(rng))
        scores[i] = metrics.overall_balance_score
    return scores


# ---------------------------------------------------------------------------
# 1. Null-model: random params underperform the configured optimizer.
# ---------------------------------------------------------------------------


def test_configured_state_clears_balance_threshold() -> None:
    """The setpoint-aligned state scores above the decision threshold T."""
    metrics = _default_optimizer()._calculate_balance_metrics(_OPTIMUM_STATE)
    assert metrics.overall_balance_score >= _BALANCE_THRESHOLD


def test_null_model_mean_underperforms_threshold() -> None:
    """A random null state distribution is, on average, below threshold T.

    This is the core null model: if the score were vacuously high for any
    input, the random mean would also clear T. It does not (null mean ~0.731,
    ~2.7 std below T = 0.95), so the optimizer's high score on the configured
    state reflects signal over chance.
    """
    scores = _null_scores()
    null_mean = float(scores.mean())
    # Margin is real, not relaxed: SEM = std/sqrt(N) is ~1.5e-3, far smaller
    # than the (T - null_mean) ~ 0.22 gap, so the inequality is not borderline.
    sem = float(scores.std(ddof=1)) / np.sqrt(_NULL_SAMPLES)
    assert null_mean < _BALANCE_THRESHOLD - 10.0 * sem


def test_configured_beats_null_with_clear_margin() -> None:
    """Configured-optimum score exceeds the null mean by a wide, derived gap.

    The gap must exceed several standard errors of the null mean so the
    separation is statistically honest rather than a seed artefact.
    """
    scores = _null_scores()
    null_mean = float(scores.mean())
    sem = float(scores.std(ddof=1)) / np.sqrt(_NULL_SAMPLES)
    configured = (
        _default_optimizer()._calculate_balance_metrics(_OPTIMUM_STATE).overall_balance_score
    )
    # Require the configured score to sit at least 20 SEM above the null mean.
    assert configured - null_mean > 20.0 * sem


def test_null_model_rarely_reaches_threshold() -> None:
    """Under the null, clearing T is rare (well under 5% of draws).

    Quantifies the false-positive rate of the threshold under chance: a random
    state only occasionally lands near both setpoints simultaneously.
    """
    scores = _null_scores()
    frac_at_threshold = float((scores >= _BALANCE_THRESHOLD).mean())
    assert frac_at_threshold < 0.05


def test_null_draw_is_deterministic() -> None:
    """Same seed -> identical null array (no hidden RNG / ordering flakiness)."""
    first = _null_scores()
    second = _null_scores()
    assert np.array_equal(first, second)


# ---------------------------------------------------------------------------
# 2. DA/5-HT and E/I are arithmetic engineering ratios (NO biological gate).
# ---------------------------------------------------------------------------


def test_ratio_ranges_accept_arbitrary_positive_reals() -> None:
    """Config accepts non-physiological ranges: only ``0 < low < high`` is required.

    There is no "physiological range" gate. A range spanning nine orders of
    magnitude is accepted without error, demonstrating the bounds are pure
    arithmetic guards, not biological constraints.
    """
    wide_low = 1e-9
    wide_high = 1e9
    numeric = NumericConfig(
        da_5ht_ratio_range=(wide_low, wide_high),
        ei_balance_range=(wide_low, wide_high),
    )
    config = OptimizationConfig(numeric=numeric)
    assert config.da_5ht_ratio_range == (wide_low, wide_high)
    assert config.ei_balance_range == (wide_low, wide_high)


def test_extreme_ratios_pass_through_without_biological_clamp() -> None:
    """With wide ranges, ratios are reported essentially unclipped.

    The only clamp is the configured arithmetic range; there is no separate
    physiological clamp. An extreme synthetic state yields an extreme ratio,
    confirming the metric is a raw arithmetic quotient.
    """
    numeric = NumericConfig(
        da_5ht_ratio_range=(1e-9, 1e9),
        ei_balance_range=(1e-9, 1e9),
    )
    optimizer = NeuroOptimizer(OptimizationConfig(numeric=numeric))
    extreme_state: Dict[str, float] = {
        "dopamine_level": 1000.0,
        "serotonin_level": 0.001,
        "gaba_inhibition": 0.001,
        "na_arousal": 1000.0,
        "ach_attention": 0.5,
    }
    metrics = optimizer._calculate_balance_metrics(extreme_state)
    # Expected DA/5-HT ~= 1000 / 0.001 = 1e6 (float32 epsilon -> ~9.99e5).
    # Far outside any plausible biological ratio, yet accepted: arithmetic only.
    assert metrics.dopamine_serotonin_ratio > 1e5
    assert metrics.gaba_excitation_balance > 1e5


def test_default_ratio_range_is_uncited_engineering_default() -> None:
    """The default bounds are the documented arithmetic defaults, nothing more.

    Pins the falsifier: the defaults ``(1.0, 3.0)`` and ``(1.0, 2.5)`` are the
    module's own constants. If a future change claims a *biological* range it
    must also supply a source; this test merely fixes the current engineering
    defaults so any silent re-anchoring to a biology claim is caught.
    """
    numeric = NumericConfig()
    assert numeric.da_5ht_ratio_range == (1.0, 3.0)
    assert numeric.ei_balance_range == (1.0, 2.5)


def test_no_physiological_range_claim_in_source() -> None:
    """Witness the NON-CLAIM directly: the source asserts no biological range.

    The remediation contract is that DA/5-HT and E/I are engineering ratios
    with no physiological-range claim. This guard fails if any biology /
    citation language is introduced for the ranges without a real source,
    flipping the module from arithmetic to a biological measurement claim.
    """
    import inspect

    from geosync.core.neuro import neuro_optimizer

    source = inspect.getsource(neuro_optimizer).lower()
    forbidden = ("physiological", "physiologic", "in vivo", "clinically")
    present = [token for token in forbidden if token in source]
    assert not present, (
        "Source introduced a biological-range claim without a cited source: "
        f"{present}. DA/5-HT and E/I must stay engineering ratios."
    )
