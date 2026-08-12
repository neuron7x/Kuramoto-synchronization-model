# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-style coverage for :mod:`core.orchestrator.mode_orchestrator`."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from core.orchestrator import (
    DelayBudget,
    GuardBand,
    GuardConfig,
    MetricsSnapshot,
    ModeOrchestrator,
    ModeOrchestratorConfig,
    ModeState,
    TimeoutConfig,
)

GUARDS = GuardConfig(
    kappa=GuardBand(soft_limit=0.85, hard_limit=0.95, recover_limit=0.6),
    var=GuardBand(soft_limit=0.75, hard_limit=0.9, recover_limit=0.5),
    max_drawdown=GuardBand(soft_limit=0.4, hard_limit=0.55, recover_limit=0.25),
    heat=GuardBand(soft_limit=0.65, hard_limit=0.85, recover_limit=0.4),
)

TIMEOUTS = TimeoutConfig(
    action_max=30.0,
    cooldown_min=5.0,
    rest_min=20.0,
    cooldown_persistence=12.0,
    safe_exit_lock=15.0,
)

DELAYS = DelayBudget(
    action_to_cooldown=0.02,
    cooldown_to_rest=0.05,
    protective_to_safe_exit=0.01,
)

CONFIG = ModeOrchestratorConfig(guards=GUARDS, timeouts=TIMEOUTS, delays=DELAYS)

SAFE_METRICS = MetricsSnapshot(kappa=0.5, var=0.4, max_drawdown=0.2, heat=0.3)


def soft_breach_snapshot(rng: random.Random) -> MetricsSnapshot:
    metrics = SAFE_METRICS
    guard_name = rng.choice(["kappa", "var", "max_drawdown", "heat"])
    band = getattr(GUARDS, guard_name)
    upper = max(band.soft_limit + 1e-6, band.hard_limit - 1e-6)
    value = rng.uniform(band.soft_limit, upper)
    return replace(metrics, **{guard_name: value})


def hard_breach_snapshot(rng: random.Random) -> MetricsSnapshot:
    metrics = SAFE_METRICS
    guard_name = rng.choice(["kappa", "var", "max_drawdown", "heat"])
    band = getattr(GUARDS, guard_name)
    value = band.hard_limit + rng.uniform(0.0, 2.0)
    return replace(metrics, **{guard_name: value})


def recovered_snapshot(rng: random.Random) -> MetricsSnapshot:
    values = {}
    for name in ["kappa", "var", "max_drawdown", "heat"]:
        band = getattr(GUARDS, name)
        lower = band.recover_limit - 1.0
        value = rng.uniform(lower, band.recover_limit)
        values[name] = value
    return replace(SAFE_METRICS, **values)


def build_orchestrator(state: ModeState, timestamp: float = 0.0) -> ModeOrchestrator:
    orchestrator = ModeOrchestrator(CONFIG)
    orchestrator.reset(state=state, timestamp=timestamp)
    return orchestrator


@pytest.mark.parametrize("seed", range(128))
def test_action_soft_breach_transitions_to_cooldown(seed: int) -> None:
    rng = random.Random(seed)
    snapshot = soft_breach_snapshot(rng)
    orchestrator = build_orchestrator(ModeState.ACTION)
    new_state = orchestrator.update(snapshot, timestamp=1.0)
    assert new_state == ModeState.COOLDOWN


@pytest.mark.parametrize("seed", range(64))
def test_action_timeout_transitions_to_cooldown(seed: int) -> None:
    rng = random.Random(seed)
    snapshot = recovered_snapshot(rng)
    orchestrator = build_orchestrator(ModeState.ACTION)
    timestamp = TIMEOUTS.action_max + 0.5
    new_state = orchestrator.update(snapshot, timestamp=timestamp)
    assert new_state == ModeState.COOLDOWN


@pytest.mark.parametrize("seed", range(128))
@pytest.mark.parametrize("state", [ModeState.ACTION, ModeState.COOLDOWN, ModeState.REST])
def test_hard_breach_forces_safe_exit(seed: int, state: ModeState) -> None:
    rng = random.Random(seed)
    snapshot = hard_breach_snapshot(rng)
    orchestrator = build_orchestrator(state)
    new_state = orchestrator.update(snapshot, timestamp=1.0)
    assert new_state == ModeState.SAFE_EXIT


@pytest.mark.parametrize("seed", range(128))
def test_cooldown_recovers_to_action_after_dwell(seed: int) -> None:
    rng = random.Random(seed)
    snapshot = recovered_snapshot(rng)
    orchestrator = build_orchestrator(ModeState.COOLDOWN)
    timestamp = TIMEOUTS.cooldown_min + 0.5
    new_state = orchestrator.update(snapshot, timestamp=timestamp)
    assert new_state == ModeState.ACTION


@pytest.mark.parametrize("seed", range(128))
def test_cooldown_persistent_violation_moves_to_rest(seed: int) -> None:
    rng = random.Random(seed)
    snapshot = soft_breach_snapshot(rng)
    orchestrator = build_orchestrator(ModeState.COOLDOWN)
    timestamp = TIMEOUTS.cooldown_persistence + 0.25
    new_state = orchestrator.update(snapshot, timestamp=timestamp)
    assert new_state == ModeState.REST


@pytest.mark.parametrize("seed", range(128))
def test_rest_recovers_to_action(seed: int) -> None:
    rng = random.Random(seed)
    snapshot = recovered_snapshot(rng)
    orchestrator = build_orchestrator(ModeState.REST)
    timestamp = TIMEOUTS.rest_min + 0.25
    new_state = orchestrator.update(snapshot, timestamp=timestamp)
    assert new_state == ModeState.ACTION


@pytest.mark.parametrize("seed", range(128))
def test_safe_exit_unlocks_to_rest(seed: int) -> None:
    rng = random.Random(seed)
    snapshot = recovered_snapshot(rng)
    orchestrator = build_orchestrator(ModeState.SAFE_EXIT)
    timestamp = TIMEOUTS.safe_exit_lock + 0.1
    new_state = orchestrator.update(snapshot, timestamp=timestamp)
    assert new_state == ModeState.REST


def test_timestamp_regression_rejected() -> None:
    orchestrator = build_orchestrator(ModeState.ACTION)
    orchestrator.update(SAFE_METRICS, timestamp=1.0)
    with pytest.raises(ValueError):
        orchestrator.update(SAFE_METRICS, timestamp=0.5)


def test_delay_budgets_non_negative() -> None:
    bad_config = ModeOrchestratorConfig(
        guards=GUARDS,
        timeouts=TIMEOUTS,
        delays=DelayBudget(
            action_to_cooldown=-1.0,
            cooldown_to_rest=DELAYS.cooldown_to_rest,
            protective_to_safe_exit=DELAYS.protective_to_safe_exit,
        ),
    )
    orchestrator = ModeOrchestrator(bad_config)
    orchestrator.reset(state=ModeState.ACTION)
    with pytest.raises(ValueError):
        orchestrator.update(soft_breach_snapshot(random.Random(0)), timestamp=1.0)
