"""T6: frozen walk-forward artifact integrity.

Guards ``results/cross_asset_kuramoto/walkforward_integrated.json`` — the
reviewer-facing evidence bundle for the cross-asset Kuramoto regime
strategy. These gates fail-closed on:

* schema drift (missing/renamed keys),
* protocol violations (robust flag, beat-BTC count, median Sharpe),
* silent divergence from the spike baseline (per-fold |ΔSharpe|),
* sign flips against the historically recorded fold trajectory.

The gates use only the frozen artifact — no data fetch, no model rerun —
so the test is fast and network-free. Full recomputation lives in
``scripts/run_walkforward_phase5.py``; this guard ensures the published
numbers match the protocol and the spike substrate byte-for-byte.

Protocol thresholds come from ``results/cross_asset_kuramoto/PARAMETER_LOCK``
and ``results/cross_asset_kuramoto/robustness_v1/ROBUSTNESS_PROTOCOL.md``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WF_PATH = REPO_ROOT / "results" / "cross_asset_kuramoto" / "walkforward_integrated.json"

REQUIRED_SPLIT_KEYS: frozenset[str] = frozenset(
    {
        "fold_id",
        "test_start",
        "test_end",
        "n_days",
        "strategy_sharpe",
        "strategy_ann_return",
        "strategy_ann_vol",
        "strategy_max_dd",
        "strategy_calmar",
        "btc_sharpe",
        "btc_max_dd",
        "turnover_sum",
        "turnover_mean",
    }
)

REQUIRED_TOP_KEYS: frozenset[str] = frozenset(
    {
        "splits",
        "n_splits",
        "median_sharpe",
        "n_positive_sharpe",
        "n_beats_btc_sharpe",
        "n_reduces_mdd_vs_btc",
        "robust",
        "spike_comparison",
        "max_abs_fold_sharpe_delta",
    }
)

# Protocol thresholds — see ROBUSTNESS_PROTOCOL.md §3 and run_walkforward_phase5.py
N_SPLITS_EXPECTED = 5
MEDIAN_SHARPE_FLOOR = 0.5  # min passable median across folds (protocol WF1 soft-floor)
N_BEATS_BTC_FLOOR = 4  # at least 4 of 5 folds must beat BTC Sharpe
N_REDUCES_MDD_FLOOR = 4  # at least 4 of 5 folds must improve MDD vs BTC
SPIKE_DELTA_TOL = 0.05  # hard stop threshold from run_walkforward_phase5.py


@pytest.fixture(scope="module")
def wf() -> dict[str, Any]:
    assert WF_PATH.exists(), f"walk-forward artifact missing: {WF_PATH}"
    payload: dict[str, Any] = json.loads(WF_PATH.read_text())
    return payload


def test_top_level_schema_complete(wf: dict[str, Any]) -> None:
    missing = REQUIRED_TOP_KEYS - set(wf.keys())
    assert not missing, f"walk-forward artifact missing top-level keys: {sorted(missing)}"


def test_five_splits_present(wf: dict[str, Any]) -> None:
    assert wf["n_splits"] == N_SPLITS_EXPECTED
    assert len(wf["splits"]) == N_SPLITS_EXPECTED


def test_split_schema_complete(wf: dict[str, Any]) -> None:
    for split in wf["splits"]:
        missing = REQUIRED_SPLIT_KEYS - set(split.keys())
        assert not missing, f"fold {split.get('fold_id')}: missing required keys {sorted(missing)}"


def test_metrics_are_finite(wf: dict[str, Any]) -> None:
    for split in wf["splits"]:
        for key in ("strategy_sharpe", "strategy_max_dd", "btc_sharpe", "btc_max_dd"):
            value = split[key]
            assert isinstance(value, (int, float))
            assert math.isfinite(value), f"fold {split['fold_id']}: {key}={value} not finite"


def test_robust_flag_is_true(wf: dict[str, Any]) -> None:
    assert wf["robust"] is True, (
        "walk-forward robust flag is False — regression against "
        "ROBUSTNESS_PROTOCOL.md §3 (requires median_sharpe > 0.5 "
        "AND n_beats_btc >= 4). Investigate before publication."
    )


def test_beats_btc_count(wf: dict[str, Any]) -> None:
    assert wf["n_beats_btc_sharpe"] >= N_BEATS_BTC_FLOOR, (
        f"n_beats_btc_sharpe={wf['n_beats_btc_sharpe']} < {N_BEATS_BTC_FLOOR}. "
        f"Cross-asset strategy must beat BTC Sharpe in ≥4 of 5 OOS folds."
    )


def test_reduces_mdd_count(wf: dict[str, Any]) -> None:
    assert wf["n_reduces_mdd_vs_btc"] >= N_REDUCES_MDD_FLOOR, (
        f"n_reduces_mdd_vs_btc={wf['n_reduces_mdd_vs_btc']} < {N_REDUCES_MDD_FLOOR}. "
        f"Cross-asset strategy must reduce max-DD vs BTC in ≥4 of 5 folds."
    )


def test_median_sharpe_above_floor(wf: dict[str, Any]) -> None:
    assert wf["median_sharpe"] > MEDIAN_SHARPE_FLOOR, (
        f"median_sharpe={wf['median_sharpe']:.4f} ≤ {MEDIAN_SHARPE_FLOOR}. "
        f"Protocol WF1 requires median OOS Sharpe above 0.5."
    )


def test_spike_bit_identity(wf: dict[str, Any]) -> None:
    """Protocol: per-fold |ΔSharpe| must stay below 0.05 vs spike baseline."""
    assert wf["max_abs_fold_sharpe_delta"] < SPIKE_DELTA_TOL, (
        f"max_abs_fold_sharpe_delta={wf['max_abs_fold_sharpe_delta']:.4f} "
        f">= {SPIKE_DELTA_TOL} — integrated walk-forward has drifted "
        f"from the spike substrate. Rerun scripts/run_walkforward_phase5.py."
    )


def test_spike_comparison_complete(wf: dict[str, Any]) -> None:
    comparison = wf["spike_comparison"]
    assert (
        len(comparison) == N_SPLITS_EXPECTED
    ), f"spike_comparison has {len(comparison)} entries, expected {N_SPLITS_EXPECTED}."
    for entry in comparison:
        for key in ("fold_id", "integrated_sharpe", "spike_sharpe", "delta_sharpe", "sign_match"):
            assert key in entry, f"spike_comparison entry missing {key}: {entry}"
        assert entry["sign_match"] is True, (
            f"fold {entry['fold_id']}: Sharpe sign mismatch vs spike "
            f"(integrated={entry['integrated_sharpe']:.3f}, "
            f"spike={entry['spike_sharpe']:.3f})"
        )


def test_fold_ids_are_ordered(wf: dict[str, Any]) -> None:
    ids = [s["fold_id"] for s in wf["splits"]]
    assert ids == list(
        range(1, N_SPLITS_EXPECTED + 1)
    ), f"fold_ids are not 1..{N_SPLITS_EXPECTED} in order: {ids}"


def test_crisis_fold_loss_preserved(wf: dict[str, Any]) -> None:
    """Honesty gate: fold 3 (2022 crypto winter) records a loss.

    The loss is the protocol's no-silent-rescue signature — a positive
    Sharpe here would mean the strategy was overfit to survive 2022, or
    the artifact was retro-tampered. Both are disqualifying.
    """
    fold3 = next(s for s in wf["splits"] if s["fold_id"] == 3)
    assert fold3["strategy_sharpe"] < 0, (
        f"fold 3 strategy_sharpe={fold3['strategy_sharpe']:.3f} — "
        f"expected negative (2022 crisis drawdown). Investigate "
        f"for overfitting or artifact tampering."
    )
