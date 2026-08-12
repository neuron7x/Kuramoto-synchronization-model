# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Occam-penalty Bayes-rule arbitration."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from research.systemic_risk.occam_penalty import (
    aic_penalized_log_likelihood,
    bic_penalized_log_likelihood,
    mdl_penalized_log_likelihood,
    occam_winner,
)


class TestAIC:
    def test_zero_params_is_log_lhood(self) -> None:
        assert aic_penalized_log_likelihood(-3.5, k=0) == -3.5

    def test_each_param_costs_one(self) -> None:
        # AIC penalty = k. Adding 1 parameter costs 1 unit of log-lhood.
        assert aic_penalized_log_likelihood(-3.5, k=1) == -4.5
        assert aic_penalized_log_likelihood(-3.5, k=5) == -8.5

    def test_invalid_k_rejected(self) -> None:
        with pytest.raises(ValueError, match="k"):
            aic_penalized_log_likelihood(-1.0, k=-1)

    def test_invalid_log_lhood_rejected(self) -> None:
        with pytest.raises(ValueError, match="log_likelihood"):
            aic_penalized_log_likelihood(math.nan, k=0)


class TestBIC:
    def test_zero_params_is_log_lhood(self) -> None:
        assert bic_penalized_log_likelihood(-3.5, k=0, n=100) == -3.5

    def test_param_cost_scales_log_n(self) -> None:
        # BIC penalty = 0.5 k log n.
        n = 100
        log_n = math.log(n)
        result = bic_penalized_log_likelihood(-3.5, k=2, n=n)
        assert result == pytest.approx(-3.5 - log_n)

    def test_invalid_n_rejected(self) -> None:
        with pytest.raises(ValueError, match="n"):
            bic_penalized_log_likelihood(-1.0, k=1, n=0)


class TestMDL:
    def test_default_c0_matches_bic(self) -> None:
        n = 50
        bic = bic_penalized_log_likelihood(-2.0, k=3, n=n)
        mdl = mdl_penalized_log_likelihood(-2.0, k=3, n=n)
        assert mdl == bic

    def test_c0_subtracts(self) -> None:
        n = 50
        bic = bic_penalized_log_likelihood(-2.0, k=3, n=n)
        mdl = mdl_penalized_log_likelihood(-2.0, k=3, n=n, c0=1.5)
        assert mdl == pytest.approx(bic - 1.5)

    def test_invalid_c0_rejected(self) -> None:
        with pytest.raises(ValueError, match="c0"):
            mdl_penalized_log_likelihood(-1.0, k=1, n=10, c0=math.inf)


class TestOccamWinner:
    def test_simpler_model_wins_when_likelihood_close(self) -> None:
        # Two models with very similar log-lhood; the one with fewer
        # parameters wins under any Occam penalty.
        wins, margin = occam_winner(
            candidate_log_lhood=-100.0,
            candidate_k=10,
            prosecutor_log_lhood=-101.0,
            prosecutor_k=2,
            n=200,
            method="BIC",
        )
        assert not wins  # candidate is more complex but barely better
        assert margin < 0

    def test_complex_candidate_wins_if_lhood_gap_large(self) -> None:
        wins, margin = occam_winner(
            candidate_log_lhood=-100.0,
            candidate_k=10,
            prosecutor_log_lhood=-150.0,
            prosecutor_k=2,
            n=200,
            method="BIC",
        )
        assert wins  # 50 nats of evidence outweigh ~21 nats of penalty
        assert margin > 0

    def test_aic_more_lenient_than_bic_for_large_n(self) -> None:
        # AIC penalty per param = 1; BIC penalty per param = 0.5 log n.
        # For n = 1000, BIC ≈ 3.45 per param > AIC.
        _, margin_aic = occam_winner(
            candidate_log_lhood=-100.0,
            candidate_k=8,
            prosecutor_log_lhood=-110.0,
            prosecutor_k=2,
            n=1000,
            method="AIC",
        )
        _, margin_bic = occam_winner(
            candidate_log_lhood=-100.0,
            candidate_k=8,
            prosecutor_log_lhood=-110.0,
            prosecutor_k=2,
            n=1000,
            method="BIC",
        )
        assert margin_aic > margin_bic

    def test_unknown_method_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown method"):
            occam_winner(
                candidate_log_lhood=-1.0,
                candidate_k=1,
                prosecutor_log_lhood=-1.0,
                prosecutor_k=1,
                n=10,
                method="EXOTIC",
            )

    @given(
        log_l_a=st.floats(min_value=-100, max_value=0, allow_nan=False),
        log_l_b=st.floats(min_value=-100, max_value=0, allow_nan=False),
        k_a=st.integers(min_value=0, max_value=10),
        k_b=st.integers(min_value=0, max_value=10),
        n=st.integers(min_value=10, max_value=10000),
    )
    def test_anti_symmetric_margin(
        self,
        log_l_a: float,
        log_l_b: float,
        k_a: int,
        k_b: int,
        n: int,
    ) -> None:
        # Swapping candidate and prosecutor flips the sign of margin.
        _, margin_ab = occam_winner(
            candidate_log_lhood=log_l_a,
            candidate_k=k_a,
            prosecutor_log_lhood=log_l_b,
            prosecutor_k=k_b,
            n=n,
            method="BIC",
        )
        _, margin_ba = occam_winner(
            candidate_log_lhood=log_l_b,
            candidate_k=k_b,
            prosecutor_log_lhood=log_l_a,
            prosecutor_k=k_a,
            n=n,
            method="BIC",
        )
        assert margin_ab == pytest.approx(-margin_ba, abs=1e-9)
