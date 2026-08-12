# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for :mod:`research.systemic_risk.falsification` (v2).

Coverage:
* :func:`auc_mann_whitney` algebraic identities (perfect / inverted /
  uniform / random).
* :func:`auc_bootstrap_ci` CI bracket sanity + degeneracy.
* :func:`bonferroni_correction` clipping + order preservation.
* End-to-end ``run_falsification`` null-AUC sanity:
  on i.i.d. random scores the per-crisis AUC must not produce
  ``HARD_PASS``; on injected pre-event signal it must produce
  ``HARD_PASS`` with both CI bounds clearing the v2 thresholds.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from research.systemic_risk.event_ledger import (
    BankingCrisisEvent,
    BankingCrisisLedger,
)
from research.systemic_risk.falsification import (
    FalsificationConfig,
    auc_bootstrap_ci,
    auc_mann_whitney,
    bonferroni_correction,
    run_falsification,
)


class TestAucMannWhitney:
    def test_perfect_separation_yields_one(self) -> None:
        pos = np.array([5.0, 6.0, 7.0])
        neg = np.array([1.0, 2.0, 3.0])
        assert auc_mann_whitney(pos, neg) == pytest.approx(1.0)

    def test_perfect_inversion_yields_zero(self) -> None:
        pos = np.array([1.0, 2.0, 3.0])
        neg = np.array([5.0, 6.0, 7.0])
        assert auc_mann_whitney(pos, neg) == pytest.approx(0.0)

    def test_identical_yields_half(self) -> None:
        pos = np.array([2.0, 2.0, 2.0])
        neg = np.array([2.0, 2.0, 2.0])
        assert auc_mann_whitney(pos, neg) == pytest.approx(0.5)

    def test_empty_returns_half_by_convention(self) -> None:
        assert auc_mann_whitney(np.array([]), np.array([1.0])) == 0.5
        assert auc_mann_whitney(np.array([1.0]), np.array([])) == 0.5

    def test_random_iid_centred_at_half(self) -> None:
        rng = np.random.default_rng(123)
        aucs = []
        for _ in range(100):
            x = rng.standard_normal(50)
            y = rng.standard_normal(50)
            aucs.append(auc_mann_whitney(x, y))
        assert abs(float(np.mean(aucs)) - 0.5) < 0.05, (
            f"INV-AUC-IID VIOLATED: mean(AUC | H0) = {np.mean(aucs):.4f}, "
            f"expected 0.5 ± 0.05 over 100 reps of size 50, seed=123"
        )


class TestAucBootstrapCi:
    def test_ci_brackets_point_estimate(self) -> None:
        rng = np.random.default_rng(7)
        pos = rng.normal(0.5, 1.0, size=80)
        neg = rng.normal(0.0, 1.0, size=80)
        point, ci_low, ci_high = auc_bootstrap_ci(pos, neg, n_bootstrap=2000)
        assert ci_low <= point <= ci_high, (
            f"INV-CI-BRACKET VIOLATED: point={point:.4f} outside "
            f"[{ci_low:.4f}, {ci_high:.4f}] at n_bootstrap=2000, seed=7"
        )

    def test_ci_under_h0_contains_half(self) -> None:
        # Under H0 (positives and negatives drawn from the same
        # distribution) the indicator I_b = [0.5 ∈ CI_b] is Bernoulli
        # with success probability equal to the actual coverage of
        # the percentile bootstrap. A correctly-calibrated 95% CI has
        # coverage 0.95 in the limit, so the count K = Σ_b I_b over
        # ``N_REPS`` independent reps is Binomial(N_REPS, 0.95).
        #
        # The acceptance threshold is the lower quantile of that
        # binomial under a chosen test-reliability level
        # ``alpha_test`` — the target rate at which a *correctly
        # implemented* bootstrap is allowed to fail this assertion by
        # sampling noise. Setting ``alpha_test = 1e-3`` keeps spurious
        # failures below 1 in 1000 CI runs, which is the "frontier-
        # lab" reliability level expected by feedback_dev_cycle.
        from scipy.stats import binom

        n_reps = 100
        nominal_coverage = 0.95
        alpha_test = 1e-3
        # binom.ppf is the quantile (smallest k with CDF(k) >= q),
        # which is the inclusive lower bound of the acceptance set.
        threshold = int(binom.ppf(alpha_test, n_reps, nominal_coverage))

        rng = np.random.default_rng(11)
        contains = 0
        for _ in range(n_reps):
            pos = rng.standard_normal(40)
            neg = rng.standard_normal(40)
            _, lo, hi = auc_bootstrap_ci(
                pos, neg, n_bootstrap=500, seed=int(rng.integers(0, 10**6))
            )
            if lo <= 0.5 <= hi:
                contains += 1
        assert contains >= threshold, (
            f"INV-CI-COVERAGE VIOLATED: 95%-nominal bootstrap CI under "
            f"H0 contained 0.5 in {contains}/{n_reps} reps; "
            f"binomial-derived lower bound at α_test={alpha_test} is "
            f"{threshold}. Under-coverage at this magnitude indicates "
            f"a calibration bug in auc_bootstrap_ci, not sampling noise."
        )

    def test_degenerate_inputs_collapse(self) -> None:
        # Single observation per arm → CI collapses to point estimate.
        pos = np.array([2.0])
        neg = np.array([1.0])
        point, lo, hi = auc_bootstrap_ci(pos, neg, n_bootstrap=100)
        assert lo == hi == point

    def test_invalid_confidence_rejected(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            auc_bootstrap_ci(np.array([1.0, 2.0]), np.array([0.0, 0.5]), confidence=0.0)

    def test_invalid_n_bootstrap_rejected(self) -> None:
        with pytest.raises(ValueError, match="n_bootstrap"):
            auc_bootstrap_ci(np.array([1.0]), np.array([0.0]), n_bootstrap=0)


class TestBonferroni:
    def test_all_zero_input(self) -> None:
        out = bonferroni_correction(np.zeros(5))
        assert np.all(out == 0.0)

    def test_all_one_input(self) -> None:
        out = bonferroni_correction(np.ones(5))
        # 5*1 clipped to 1.
        assert np.all(out == 1.0)

    def test_simple_case(self) -> None:
        p = np.array([0.005, 0.01, 0.04, 0.5])
        out = bonferroni_correction(p)
        np.testing.assert_allclose(out, [0.02, 0.04, 0.16, 1.0], atol=1e-12)

    def test_order_preserved(self) -> None:
        p = np.array([0.5, 0.005, 0.04, 0.01])
        out = bonferroni_correction(p)
        # min input at index 1 → 4 * 0.005 = 0.02.
        assert out[1] == pytest.approx(0.02)

    def test_invalid_p_rejected(self) -> None:
        with pytest.raises(ValueError):
            bonferroni_correction(np.array([-0.1, 0.5]))
        with pytest.raises(ValueError):
            bonferroni_correction(np.array([0.5, 1.5]))


class TestRunFalsificationSanity:
    def _build_synthetic_ledger_and_score(
        self,
        seed: int,
    ) -> tuple[BankingCrisisLedger, tuple[date, ...], np.ndarray]:
        start = date(2010, 1, 1)
        n_days = 365 * 8
        dates = tuple(start + timedelta(days=i) for i in range(n_days))
        events = (
            BankingCrisisEvent(
                country="ABC",
                start=date(2011, 6, 1),
                end=date(2011, 12, 31),
                source="LV2018",
                label="A_2011",
            ),
            BankingCrisisEvent(
                country="ABC",
                start=date(2013, 3, 1),
                end=date(2013, 9, 30),
                source="LV2018",
                label="A_2013",
            ),
            BankingCrisisEvent(
                country="ABC",
                start=date(2015, 1, 1),
                end=date(2015, 6, 30),
                source="LV2018",
                label="A_2015",
            ),
        )
        ledger = BankingCrisisLedger(events=events)
        rng = np.random.default_rng(seed)
        score = rng.standard_normal(n_days).astype(np.float64)
        return ledger, dates, score

    def test_random_scores_do_not_pass(self) -> None:
        ledger, dates, score = self._build_synthetic_ledger_and_score(seed=42)
        cfg = FalsificationConfig(
            pre_event_window_days=60,
            null_window_count=10,
            min_distance_from_event_days=180,
            n_permutations=200,
            n_bootstrap=500,
            seed=7,
        )
        report = run_falsification(score, dates, ledger, config=cfg, country_filter="ABC")
        assert report.verdict != "HARD_PASS"
        assert report.verdict in {"HARD_FAIL", "UNDECIDED"}

    def test_injected_signal_passes(self) -> None:
        ledger, dates, score = self._build_synthetic_ledger_and_score(seed=42)
        # Inject +3σ elevation in the 60-day pre-event window of every crisis.
        for ev in ledger.events:
            delta = (ev.start - dates[0]).days
            if delta - 60 < 0:
                continue
            score[delta - 60 : delta] += 3.0
        cfg = FalsificationConfig(
            pre_event_window_days=60,
            null_window_count=15,
            min_distance_from_event_days=180,
            n_permutations=2000,
            n_bootstrap=2000,
            seed=11,
        )
        report = run_falsification(score, dates, ledger, config=cfg, country_filter="ABC")
        assert report.verdict == "HARD_PASS", (
            f"INJECTED-SIGNAL VIOLATED: verdict={report.verdict}, "
            f"expected HARD_PASS at +3σ injection across 3 crises. "
            f"outcomes: {[(o.label, round(o.auc, 3), round(o.auc_ci_low, 3)) for o in report.outcomes]}"
        )
        for o in report.outcomes:
            assert o.auc_ci_low >= 0.70, (
                f"PASS-THRESHOLD VIOLATED: {o.label} auc_ci_low={o.auc_ci_low:.4f} "
                f"< 0.70 at +3σ injection, n_bootstrap=2000, seed=11"
            )

    def test_score_length_mismatch_rejected(self) -> None:
        ledger, dates, _ = self._build_synthetic_ledger_and_score(seed=0)
        with pytest.raises(ValueError, match="score length"):
            run_falsification(np.zeros(10, dtype=np.float64), dates, ledger)

    def test_non_monotone_dates_rejected(self) -> None:
        ledger = BankingCrisisLedger(events=tuple())
        bad_dates = (date(2010, 1, 1), date(2010, 1, 1))
        with pytest.raises(ValueError, match="strictly increasing"):
            run_falsification(np.zeros(2, dtype=np.float64), bad_dates, ledger)


class TestScopeExplicitAliases:
    def _build(
        self,
    ) -> tuple[BankingCrisisLedger, tuple[date, ...], np.ndarray]:
        return TestRunFalsificationSanity()._build_synthetic_ledger_and_score(seed=42)

    def test_score_level_alias_matches_run_falsification(self) -> None:
        from research.systemic_risk.falsification import run_score_level_falsification

        ledger, dates, score = self._build()
        cfg = FalsificationConfig(
            pre_event_window_days=60,
            null_window_count=10,
            min_distance_from_event_days=180,
            n_permutations=200,
            n_bootstrap=500,
            seed=7,
        )
        a = run_falsification(score, dates, ledger, config=cfg, country_filter="ABC")
        b = run_score_level_falsification(score, dates, ledger, config=cfg, country_filter="ABC")
        assert a.verdict == b.verdict
        assert len(a.outcomes) == len(b.outcomes)
        for oa, ob in zip(a.outcomes, b.outcomes):
            assert oa.label == ob.label
            assert oa.auc == ob.auc

    def test_end_to_end_falsification_fails_closed(self) -> None:
        from research.systemic_risk.falsification import run_end_to_end_falsification

        with pytest.raises(NotImplementedError, match="end-to-end|null-audit"):
            run_end_to_end_falsification()
