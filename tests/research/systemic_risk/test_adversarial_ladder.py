# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adversarial-ladder verdict tests.

Default verdict is GUILTY. Acquittal requires the candidate to clear
*every* engaged prosecutor with paired-bootstrap delta CI lower bound
above ``delta_floor``. Even an acquittal on the engaged set is
labelled ``ACQUITTED_ENGAGED`` — the four external rungs (4, 6, 7, 8)
remain in ``untested_rungs``.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from research.systemic_risk.adversarial_ladder import (
    LADDER_RUNGS,
    LadderConfig,
    ProsecutorScore,
    parameter_fragility_audit,
    run_adversarial_ladder,
    run_null_audit,
)
from research.systemic_risk.event_ledger import (
    BankingCrisisEvent,
    BankingCrisisLedger,
)
from research.systemic_risk.falsification import FalsificationConfig


def _build_synthetic_setup(
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


def _injected_signal(
    score: np.ndarray, dates: tuple[date, ...], ledger: BankingCrisisLedger
) -> np.ndarray:
    """Return a copy of ``score`` with +3σ elevation in 60d pre-event windows."""
    out = score.copy()
    for ev in ledger.events:
        delta_days = (ev.start - dates[0]).days
        if delta_days - 60 < 0:
            continue
        out[delta_days - 60 : delta_days] += 3.0
    return out


def _fast_falsification_config() -> FalsificationConfig:
    return FalsificationConfig(
        pre_event_window_days=60,
        null_window_count=10,
        min_distance_from_event_days=180,
        n_permutations=200,
        n_bootstrap=300,
        seed=7,
    )


def _fast_ladder_config() -> LadderConfig:
    return LadderConfig(
        falsification=_fast_falsification_config(),
        seed=11,
        n_bootstrap=500,
    )


class TestLadderRungs:
    def test_canonical_eight_rungs(self) -> None:
        # The ladder must enumerate every rung in 1..8 exactly once.
        ranks = [r for r, _ in LADDER_RUNGS]
        assert ranks == list(range(1, 9))


class TestLadderVerdictDefaults:
    def test_default_verdict_is_guilty_under_random_signal(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        # Prosecutor = injected signal; candidate = random noise →
        # candidate cannot beat the prosecutor → GUILTY.
        prose = _injected_signal(score.copy(), dates, ledger)
        report = run_adversarial_ladder(
            score,
            dates,
            ledger,
            prosecutors=(ProsecutorScore(name="injected_signal", rung=1, score=prose),),
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        assert report.verdict == "GUILTY"
        assert "injected_signal" in report.losing_paths
        assert report.lowest_rung_loss == 1

    def test_zero_prosecutors_yields_insufficient(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        report = run_adversarial_ladder(
            score,
            dates,
            ledger,
            prosecutors=tuple(),
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        assert report.verdict == "INSUFFICIENT_RUNGS"
        # All eight rungs must be in untested_rungs.
        assert set(report.untested_rungs) == set(range(1, 9))

    def test_acquitted_engaged_requires_all_engaged_to_lose(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        # Candidate = injected; prosecutors = random noise + slightly
        # weaker injected → candidate beats both.
        candidate = _injected_signal(score.copy(), dates, ledger)
        rng = np.random.default_rng(101)
        prose1 = rng.standard_normal(score.size).astype(np.float64)
        prose2 = score.copy() + rng.standard_normal(score.size).astype(np.float64) * 0.2
        report = run_adversarial_ladder(
            candidate,
            dates,
            ledger,
            prosecutors=(
                ProsecutorScore(name="random", rung=1, score=prose1),
                ProsecutorScore(name="weak_noise", rung=2, score=prose2),
            ),
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        assert report.verdict == "ACQUITTED_ENGAGED"
        assert set(report.survival_paths) == {"random", "weak_noise"}
        # Untested rungs must include 3-8 (we engaged only 1 and 2).
        assert set(report.untested_rungs) == {3, 4, 5, 6, 7, 8}

    def test_one_loss_anywhere_yields_guilty(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        candidate = _injected_signal(score.copy(), dates, ledger)
        # Prosecutor 1 (rung 1) is random noise — candidate beats it.
        rng = np.random.default_rng(101)
        prose_easy = rng.standard_normal(score.size).astype(np.float64)
        # Prosecutor 2 (rung 2) is the SAME injected signal — perfect
        # parity, paired delta ≈ 0 → ci_low fails delta_floor=0.0.
        prose_tied = candidate.copy()
        report = run_adversarial_ladder(
            candidate,
            dates,
            ledger,
            prosecutors=(
                ProsecutorScore(name="easy", rung=1, score=prose_easy),
                ProsecutorScore(name="tied", rung=2, score=prose_tied),
            ),
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        # Even if we beat prosecutor 1, the tie at rung 2 → GUILTY.
        assert report.verdict == "GUILTY"
        assert "tied" in report.losing_paths
        assert report.lowest_rung_loss == 2

    def test_length_mismatch_records_failure_reason(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        bad = ProsecutorScore(
            name="wrong_len",
            rung=1,
            score=np.zeros(score.size - 5, dtype=np.float64),
        )
        report = run_adversarial_ladder(
            score,
            dates,
            ledger,
            prosecutors=(bad,),
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        assert report.verdict == "GUILTY"
        outcome = report.outcomes[0]
        assert outcome.failure_reason is not None
        assert "length" in outcome.failure_reason


class TestLadderConfig:
    def test_negative_delta_floor_rejected(self) -> None:
        with pytest.raises(ValueError, match="delta_floor"):
            LadderConfig(
                falsification=_fast_falsification_config(),
                delta_floor=-0.01,
            )

    def test_low_n_bootstrap_rejected(self) -> None:
        with pytest.raises(ValueError, match="n_bootstrap"):
            LadderConfig(
                falsification=_fast_falsification_config(),
                n_bootstrap=10,
            )


class TestProsecutorScore:
    def test_invalid_rung_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"rung.*\[1, 8\]"):
            ProsecutorScore(name="bad", rung=0, score=np.zeros(5))
        with pytest.raises(ValueError, match=r"rung.*\[1, 8\]"):
            ProsecutorScore(name="bad", rung=9, score=np.zeros(5))

    def test_non_1d_score_rejected(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            ProsecutorScore(name="bad", rung=1, score=np.zeros((5, 5)))


class TestParameterFragilityAudit:
    def test_sweep_records_per_value_auc(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        candidate = _injected_signal(score.copy(), dates, ledger)
        out = parameter_fragility_audit(
            candidate,
            dates,
            ledger,
            base_config=_fast_falsification_config(),
            parameter="pre_event_window_days",
            sweep=(45.0, 60.0, 75.0),
            country_filter="ABC",
        )
        assert out.parameter == "pre_event_window_days"
        assert out.values == (45.0, 60.0, 75.0)
        assert len(out.aucs) == 3
        assert len(out.verdicts) == 3
        assert np.isfinite(out.auc_min)

    def test_unknown_parameter_rejected(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        with pytest.raises(ValueError, match="sweep-eligible"):
            parameter_fragility_audit(
                score,
                dates,
                ledger,
                base_config=_fast_falsification_config(),
                parameter="not_a_real_field",
                sweep=(1.0,),
                country_filter="ABC",
            )

    def test_empty_sweep_rejected(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        with pytest.raises(ValueError, match="sweep must be non-empty"):
            parameter_fragility_audit(
                score,
                dates,
                ledger,
                base_config=_fast_falsification_config(),
                parameter="pre_event_window_days",
                sweep=tuple(),
                country_filter="ABC",
            )

    def test_fragility_flag_responds_to_tolerance(self) -> None:
        # Build a setup where the AUC genuinely varies across windows
        # — by injecting a narrow pre-event spike that only the
        # narrowest window fully captures.
        ledger, dates, score = _build_synthetic_setup(seed=42)
        # Spike only in days [E - 20, E - 1] for each event.
        candidate = score.copy()
        for ev in ledger.events:
            delta_days = (ev.start - dates[0]).days
            if delta_days - 20 < 0:
                continue
            candidate[delta_days - 20 : delta_days] += 5.0
        out = parameter_fragility_audit(
            candidate,
            dates,
            ledger,
            base_config=_fast_falsification_config(),
            parameter="pre_event_window_days",
            sweep=(20.0, 60.0, 120.0),
            fragility_tolerance=0.0,  # any nonzero range = fragile
            country_filter="ABC",
        )
        # Different windows produce different AUCs by construction.
        assert out.fragile or out.auc_range > 0.0


class TestRunNullAudit:
    def test_pins_every_surrogate_to_rung_two(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        rng = np.random.default_rng(101)
        nulls = (
            ("shuffled_time_labels", rng.permutation(score)),
            ("linear_correlation_surrogate", rng.standard_normal(score.size)),
        )
        report = run_null_audit(
            score,
            nulls,
            dates,
            ledger,
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        for outcome in report.outcomes:
            assert outcome.rung == 2, (
                f"run_null_audit must pin every surrogate to rung 2; "
                f"got {outcome.name} at rung {outcome.rung}"
            )

    def test_partial_audit_lists_remaining_rungs(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        rng = np.random.default_rng(101)
        nulls = (("shuffled_time_labels", rng.permutation(score)),)
        report = run_null_audit(
            score,
            nulls,
            dates,
            ledger,
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        # Only rung 2 is engaged → all other rungs untested.
        assert set(report.untested_rungs) == {1, 3, 4, 5, 6, 7, 8}

    def test_zero_nulls_yields_insufficient(self) -> None:
        ledger, dates, score = _build_synthetic_setup(seed=42)
        report = run_null_audit(
            score,
            tuple(),
            dates,
            ledger,
            config=_fast_ladder_config(),
            country_filter="ABC",
        )
        assert report.verdict == "INSUFFICIENT_RUNGS"
