# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for risk core module."""

import numpy as np
import pytest

from geosync.risk.risk_core import (
    RiskConfig,
    check_risk_breach,
    compute_final_size,
    kelly_shrink,
    var_es,
)


class TestVarES:
    """Test VaR and ES calculations."""

    def test_normal_returns(self):
        """Test VaR/ES on normal distributed returns."""
        np.random.seed(42)
        returns = np.random.randn(1000) * 0.02

        var, es = var_es(returns, alpha=0.95)

        assert var > 0
        assert es > 0
        assert es >= var

    def test_handles_non_finite_inputs(self):
        """Non-finite inputs should be ignored safely."""
        returns = np.array([0.01, np.nan, 0.02, np.inf, -0.03])

        var, es = var_es(returns, alpha=0.95)

        assert np.isfinite(var)
        assert np.isfinite(es)
        assert es >= var

    def test_empty_input_fails_closed_to_breach(self):
        """All-NaN/empty input has UNKNOWN risk, not zero.

        Regression for a fail-open defect: var_es previously returned
        (0.0, 0.0) when no finite returns remained, a *legal* riskless ES that
        check_risk_breach would read as "OK". It must instead be non-finite so
        the downstream breach check fails closed.
        """
        returns = np.array([np.nan, np.inf, -np.inf])

        var, es = var_es(returns, alpha=0.95)

        assert not np.isfinite(es), "empty-input ES must be non-finite (fail-closed)"
        assert not np.isfinite(var), "empty-input VaR must be non-finite (fail-closed)"
        # The fail-closed sentinel must be treated as a breach downstream.
        assert check_risk_breach(es, es_limit=0.03) == "BREACH"

    def test_expected_shortfall_is_the_tail_mean_not_the_quantile(self):
        """`if len(tail_losses) > 0` decides whether ES is the TAIL MEAN or just VaR again.

        Every existing case asserts only `es >= var`, which the degenerate answer `es = var`
        satisfies — so a mutation probe left `Gt -> LtE` alive. Under that mutant ES collapses
        onto VaR for every input, systematically understating tail risk on exactly the
        fat-tailed distributions ES exists to measure. What actually kills the mutant is the
        algorithm-free `es > var` below; the re-derivation that follows re-implements the same
        quantile-and-tail-mean recipe, so it pins the arithmetic without being an independent
        oracle. Both are stated for what they are.
        """
        # 99 small losses and one catastrophic one: at alpha=0.95 the tail holds the extreme.
        returns = np.concatenate([np.full(99, -0.01), np.array([-1.0])])

        var, es = var_es(returns, alpha=0.95)

        losses = -returns
        expected_var = float(np.quantile(losses, 0.95))
        expected_es = float(np.mean(losses[losses >= expected_var]))

        assert es == pytest.approx(expected_es)
        assert es > var, (
            f"ES ({es}) collapsed onto VaR ({var}) — the tail mean was not taken, so a "
            "catastrophic tail is priced as an ordinary one"
        )

    def test_expected_shortfall_equals_var_when_the_tail_is_degenerate(self):
        """Matched control: identical losses give ES == VaR legitimately.

        This case kills no mutant and is not meant to — it exists so the assertion above
        cannot be satisfied by a rule as crude as "ES must always exceed VaR".
        """
        returns = np.full(64, -0.02)

        var, es = var_es(returns, alpha=0.95)

        assert var == pytest.approx(0.02)
        assert es == pytest.approx(var)


class TestKellyShrink:
    """Test Kelly fraction with shrinkage."""

    def test_emergent_no_shrink(self):
        """Test EMERGENT state with no shrinkage."""
        f = kelly_shrink(0.001, 0.0004, "EMERGENT", 1.0)
        assert abs(f - 1.0) < 0.01

    def test_caution_half_shrink(self):
        """Test CAUTION state with half shrinkage."""
        f = kelly_shrink(0.001, 0.0004, "CAUTION", 1.0)
        assert abs(f - 0.5) < 0.01

    def test_kill_zero_size(self):
        """Test KILL state with zero sizing."""
        f = kelly_shrink(0.001, 0.0004, "KILL", 1.0)
        assert f == 0.0

    @pytest.mark.parametrize(
        "bad_regime",
        ["UNKNOWN", "CATASTROPHE", "kill", "Caution", "EMERGENT ", "", None],
    )
    def test_unknown_regime_fails_closed_to_zero(self, bad_regime):
        """Unrecognized/None/empty/wrong-case EWS regime must size to ZERO.

        Regression for DS-05 (fail-OPEN): kelly_shrink previously defaulted an
        unrecognized ews_level to lambda=0.5, laundering a HALF position size
        past risk sizing for corrupted, new, or MORE-SEVERE early-warning
        states. Exact-match contract: wrong-case ("kill") and whitespace
        ("EMERGENT ") are NOT silently case-/space-folded — they are unknown
        and must fail closed to 0.0.
        """
        f = kelly_shrink(0.001, 0.0004, bad_regime, 1.0)
        assert f == 0.0, (
            f"DS-05 fail-OPEN: unknown EWS regime {bad_regime!r} returned "
            f"f={f} (expected 0.0 fail-closed). A non-flat size for an "
            f"unrecognized regime is a safety inversion."
        )

    def test_recognized_regimes_unchanged(self):
        """Non-vacuous guard: recognized regimes keep their EXACT prior factors.

        The fail-closed default must not perturb the known shrink factors:
        KILL=0.0, CAUTION=0.5, EMERGENT=1.0 of the raw Kelly f=mu/sigma2.
        """
        mu, sigma2 = 0.001, 0.0004
        f_raw = mu / sigma2  # 2.5, capped to f_max=1.0
        capped = min(1.0, f_raw)
        assert kelly_shrink(mu, sigma2, "KILL", 1.0) == 0.0 * capped
        assert kelly_shrink(mu, sigma2, "CAUTION", 1.0) == 0.5 * capped
        assert kelly_shrink(mu, sigma2, "EMERGENT", 1.0) == 1.0 * capped


class TestComputeFinalSize:
    """Test final size computation."""

    def test_basic_sizing(self):
        """Test basic size computation."""
        size = compute_final_size(0.8, 0.5, 1.0)
        assert abs(size - 0.4) < 0.01


class TestCheckRiskBreach:
    """Test risk breach checking."""

    def test_no_breach(self):
        """Test when ES is below limit."""
        state = check_risk_breach(0.02, 0.03)
        assert state == "OK"

    def test_breach(self):
        """Test when ES exceeds limit."""
        state = check_risk_breach(0.04, 0.03)
        assert state == "BREACH"

    def test_non_finite_es_flags_breach(self):
        """Non-finite ES should be treated as a breach for safety."""
        state = check_risk_breach(float("nan"), 0.03)
        assert state == "BREACH"


class TestRiskConfig:
    """Test risk configuration handling."""

    def test_respects_zero_overrides(self, monkeypatch):
        """Explicit zero values should not fall back to env defaults."""
        monkeypatch.setenv("TP_ES_LIMIT", "0.10")
        monkeypatch.setenv("TP_VAR_ALPHA", "0.90")
        monkeypatch.setenv("TP_FMAX", "0.50")

        cfg = RiskConfig(es_limit=0.0, var_alpha=0.0, f_max=0.0)

        assert cfg.es_limit == 0.0
        assert cfg.var_alpha == 0.0
        assert cfg.f_max == 0.0

    def test_env_defaults_used_when_none(self, monkeypatch):
        """Environment variables should provide defaults when params omitted."""
        monkeypatch.setenv("TP_ES_LIMIT", "0.07")
        monkeypatch.setenv("TP_VAR_ALPHA", "0.93")
        monkeypatch.setenv("TP_FMAX", "0.75")

        cfg = RiskConfig()

        assert cfg.es_limit == pytest.approx(0.07)
        assert cfg.var_alpha == pytest.approx(0.93)
        assert cfg.f_max == pytest.approx(0.75)
