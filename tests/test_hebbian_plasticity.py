# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,arg-type"
"""Tests for Reward-Modulated Hebbian Plasticity."""

from __future__ import annotations

from geosync.neuroeconomics.hebbian_plasticity import HebbianPlasticity, PlasticWeights


def test_ltp_strengthens_excitatory_on_profit() -> None:
    hp = HebbianPlasticity(lr_init=0.05)
    before = hp.weights.ei_ex_risk
    hp.update(decision="TRADE", pnl=0.1, regime="METASTABLE")
    after = hp.weights.ei_ex_risk
    assert after > before, f"LTP should strengthen: {before} → {after}"


def test_ltd_weakens_excitatory_on_loss() -> None:
    hp = HebbianPlasticity(lr_init=0.05)
    before = hp.weights.ei_ex_risk
    hp.update(decision="TRADE", pnl=-0.1, regime="METASTABLE")
    after = hp.weights.ei_ex_risk
    assert after < before, f"LTD should weaken: {before} → {after}"


def test_observe_reinforced_when_avoided_loss() -> None:
    hp = HebbianPlasticity(lr_init=0.05)
    before = hp.weights.ep_uncertainty
    hp.update(decision="OBSERVE", pnl=-0.1, regime="CRITICAL")
    after = hp.weights.ep_uncertainty
    assert after > before, "OBSERVE that avoided loss should reinforce epistemic"


def test_weights_never_go_below_floor() -> None:
    hp = HebbianPlasticity(lr_init=0.5, weight_floor=0.05)
    for _ in range(100):
        hp.update(decision="TRADE", pnl=-1.0, regime="DECOHERENT")
    w = hp.weights.to_list()
    assert all(v >= 0.05 for v in w), f"Weight below floor: {w}"


def test_learning_rate_decays() -> None:
    hp = HebbianPlasticity(lr_init=0.1, lr_decay=0.9)
    lr_before = hp._lr
    for _ in range(10):
        hp.update(decision="TRADE", pnl=0.01, regime="METASTABLE")
    assert hp._lr < lr_before


def test_learning_rate_has_floor() -> None:
    hp = HebbianPlasticity(lr_init=0.1, lr_decay=0.5, lr_floor=0.01)
    for _ in range(100):
        hp.update(decision="TRADE", pnl=0.01, regime="METASTABLE")
    assert hp._lr >= 0.01


def test_consolidation_snapshots_best() -> None:
    hp = HebbianPlasticity(lr_init=0.02, consolidation_interval=10)
    # 10 profitable trades → consolidate
    for _ in range(10):
        hp.update(decision="TRADE", pnl=0.05, regime="METASTABLE")
    state = hp.state()
    assert state.consolidation_count >= 0
    assert isinstance(state.best_sharpe, float)


def test_restore_best_recovers_from_degradation() -> None:
    hp = HebbianPlasticity(lr_init=0.05, consolidation_interval=10)
    # Phase 1: profitable → consolidate good weights
    for _ in range(15):
        hp.update(decision="TRADE", pnl=0.05, regime="METASTABLE")
    good_risk = hp._best_weights.ei_ex_risk

    # Phase 2: losses degrade weights
    for _ in range(20):
        hp.update(decision="TRADE", pnl=-0.1, regime="CRITICAL")

    # Weights degraded
    assert hp.weights.ei_ex_risk < good_risk

    # Restore best
    hp.restore_best()
    assert hp.weights.ei_ex_risk == good_risk


def test_no_update_on_zero_pnl_trade() -> None:
    hp = HebbianPlasticity(lr_init=0.05)
    before = hp.weights.to_list()
    hp.update(decision="TRADE", pnl=0.0, regime="METASTABLE")
    after = hp.weights.to_list()
    assert before == after, "Zero PnL should not change weights"


def test_plastic_weights_roundtrip() -> None:
    pw = PlasticWeights()
    original = pw.to_list()
    pw2 = PlasticWeights()
    pw2.from_list(original)
    assert pw2.to_list() == original


def test_state_tracks_ltp_ltd_counts() -> None:
    hp = HebbianPlasticity()
    hp.update(decision="TRADE", pnl=0.1, regime="METASTABLE")
    hp.update(decision="TRADE", pnl=0.1, regime="METASTABLE")
    hp.update(decision="TRADE", pnl=-0.1, regime="CRITICAL")
    state = hp.state()
    assert state.total_ltp == 2
    assert state.total_ltd == 1
