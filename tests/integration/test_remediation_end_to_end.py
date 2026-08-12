# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end witness that T/E/X/P axes work together.

Scenario:
    1. Install a FrozenClock via ``use_clock`` (T-axis).
    2. Construct a PostgresEventStore against SQLite with both the
       clock and a ``default_gate()`` admission surface (E-axis).
    3. Apply a runtime policy change via ``apply_policy_change``
       (P-axis).
    4. Drive env overrides through ``IsolatedEnv`` (X-axis).
    5. Verify every piece stays deterministic and no state leaks.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import JSON, Integer, create_engine

from core.events.admission import default_gate
from core.events.sourcing import (
    OrderAggregate,
    OrderFilled,
    PostgresEventStore,
)
from core.events.validation import DomainValidationError
from cortex_service.app.config import RegimeSettings
from cortex_service.app.modulation.regime import (
    ExponentialDecayPolicy,
    PolicyRegistry,
    RegimeModulator,
    apply_policy_change,
)
from domain.order import OrderSide, OrderStatus, OrderType
from geosync.core.compat import FrozenClock, use_clock
from tests.fixtures.isolation import IsolatedEnv


class _FlatPolicy:
    def __init__(self, v: float, c: float) -> None:
        self.v = v
        self.c = c

    def compute(self, previous, feedback, volatility):  # noqa: D401 - protocol impl
        return self.v, self.c


def _prepare_store(engine, clock):
    store = PostgresEventStore(engine, schema=None, clock=clock)
    for table in (store._events, store._snapshots):
        for col in table.columns:
            if col.name == "metadata":
                col.server_default = None
    store.create_schema()
    return store


@pytest.fixture
def patched_engine_factory(monkeypatch):
    monkeypatch.setattr("core.events.sourcing.JSONB", JSON, raising=True)
    monkeypatch.setattr("core.events.sourcing.BigInteger", Integer, raising=True)
    return lambda: create_engine("sqlite:///:memory:", future=True)


class TestFourAxisEndToEnd:
    def test_frozen_clock_drives_event_store_and_audit(self, patched_engine_factory) -> None:
        """T-axis: the FrozenClock is the single source of time."""
        instant = datetime(2026, 6, 1, tzinfo=timezone.utc)
        clock = FrozenClock(instant=instant)
        with use_clock(clock):
            store = _prepare_store(patched_engine_factory(), clock)
            agg = OrderAggregate.create(
                order_id="o-e2e",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10.0,
                price=150.0,
                order_type=OrderType.LIMIT,
            )
            store.append(
                aggregate=agg,
                events=agg.get_pending_events(),
                expected_version=0,
            )
            agg.clear_pending_events()

            envelopes = store.load_stream(aggregate_id=agg.id, aggregate_type=agg.aggregate_type)
            # Every row carries the FrozenClock's epoch_ns — identical
            # across replays because the clock does not advance.
            assert envelopes[0].epoch_ns == clock.epoch_ns()

    def test_admission_gate_rejects_overfill_through_store(self, patched_engine_factory) -> None:
        """E-axis: four-barrier gate wired through append()."""
        clock = FrozenClock(instant=datetime(2026, 6, 1, tzinfo=timezone.utc))
        store = _prepare_store(patched_engine_factory(), clock)
        agg = OrderAggregate.create(
            order_id="o-e2e",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10.0,
            price=150.0,
            order_type=OrderType.LIMIT,
        )
        agg.clear_pending_events()
        bad = OrderFilled(
            order_id=agg.id,
            fill_quantity=999.0,
            fill_price=150.0,
            cumulative_quantity=999.0,
            average_price=150.0,
            status=OrderStatus.FILLED,
        )
        with pytest.raises(DomainValidationError) as exc:
            store.append(
                aggregate=agg,
                events=[bad],
                expected_version=0,
                admission_gate=default_gate(),
            )
        # The raised error carries the machine-readable reject code
        # from the gate, not just free-form text — a forensic trail.
        message = str(exc.value)
        assert "E_STATE_INCONSISTENT" in message
        assert "B3_STATE" in message
        assert "exceeds remaining" in message

        # And nothing was persisted.
        envelopes = store.load_stream(aggregate_id=agg.id, aggregate_type=agg.aggregate_type)
        assert envelopes == []

    def test_policy_hot_swap_through_registry(self) -> None:
        """P-axis: runtime reconfiguration leaves no dropped tick."""
        settings = RegimeSettings(
            decay=0.3, min_valence=-1.0, max_valence=1.0, confidence_floor=0.1
        )
        modulator = RegimeModulator(settings)
        registry = PolicyRegistry()
        registry.register("flat_bull", lambda: _FlatPolicy(0.8, 0.9))
        previous = apply_policy_change(modulator, registry, "flat_bull")

        assert isinstance(previous, ExponentialDecayPolicy)
        state = modulator.update(
            None,
            feedback=-1.0,
            volatility=0.5,
            as_of=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        # Flat policy ignores inputs — confirms the swap took effect
        # immediately on the very next tick.
        assert state.valence == pytest.approx(0.8)
        assert state.confidence == pytest.approx(0.9)

    def test_env_isolation_does_not_leak(self) -> None:
        """X-axis: IsolatedEnv restores state after the block."""
        key = "GEOSYNC_E2E_ISOLATION_WITNESS"
        assert key not in os.environ
        with IsolatedEnv({key: "inside"}):
            assert os.environ[key] == "inside"
        assert key not in os.environ

    def test_combined_flow(self, patched_engine_factory) -> None:
        """All four axes in one scenario: frozen time, gate-protected
        write, policy swap, env isolation — and nothing leaks."""
        key = "GEOSYNC_E2E_COMBINED"
        instant = datetime(2026, 6, 1, tzinfo=timezone.utc)
        clock = FrozenClock(instant=instant)

        with IsolatedEnv({key: "on"}), use_clock(clock):
            store = _prepare_store(patched_engine_factory(), clock)
            modulator = RegimeModulator(
                RegimeSettings(
                    decay=0.3,
                    min_valence=-1.0,
                    max_valence=1.0,
                    confidence_floor=0.1,
                )
            )
            registry = PolicyRegistry()
            registry.register("flat", lambda: _FlatPolicy(0.5, 0.5))
            apply_policy_change(modulator, registry, "flat")

            agg = OrderAggregate.create(
                order_id="o-combined",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=5.0,
                price=200.0,
                order_type=OrderType.LIMIT,
            )
            store.append(
                aggregate=agg,
                events=agg.get_pending_events(),
                expected_version=0,
                admission_gate=default_gate(),
            )
            agg.clear_pending_events()
            envelopes = store.load_stream(aggregate_id=agg.id, aggregate_type=agg.aggregate_type)
            assert envelopes[0].epoch_ns == clock.epoch_ns()
            state = modulator.update(
                None,
                feedback=0.1,
                volatility=0.1,
                as_of=instant,
            )
            assert state.valence == pytest.approx(0.5)

        # Env and clock both restored after the block exits.
        assert key not in os.environ
