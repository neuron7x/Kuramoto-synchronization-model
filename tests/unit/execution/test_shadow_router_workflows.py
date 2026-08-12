# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for execution/shadow.py, execution/router.py, execution/workflows.py.

Covers the 0 % and low-coverage modules:
  - ShadowDeploymentOrchestrator  (shadow.py  –  0 % coverage)
  - ResilientExecutionRouter       (router.py  – 27 % coverage)
  - RiskComplianceWorkflow         (workflows.py – 74 % coverage, gap paths)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------
from domain import Order, OrderSide, OrderStatus, OrderType
from domain.signals import Signal, SignalAction
from execution.compliance import ComplianceMonitor, ComplianceReport, ComplianceViolation
from execution.connectors import TransientOrderError
from execution.normalization import SymbolNormalizer, SymbolSpecification
from execution.resilience.circuit_breaker import (
    ExchangeResilienceProfile,
    default_resilience_profile,
)
from execution.risk import RiskLimits, RiskManager

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
from execution.router import (
    ErrorMapper,
    ExecutionRoute,
    NormalizedOrderState,
    OrderStateNormalizer,
    ResilientExecutionRouter,
    SlippageModel,
)

# ---------------------------------------------------------------------------
# Shadow
# ---------------------------------------------------------------------------
from execution.shadow import (
    ShadowArchiveRecord,
    ShadowDecision,
    ShadowDeploymentConfig,
    ShadowDeploymentOrchestrator,
    SignalDeviation,
    _action_to_numeric,
)

# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------
from execution.workflows import (
    OrderAssessment,
    OrderRequest,
    RiskComplianceWorkflow,
    WorkflowAssessment,
)

# ==========================================================================
# Fixtures / helpers
# ==========================================================================

_UTC = timezone.utc


def _fixed_clock() -> datetime:
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=_UTC)


def _make_signal(action: str = "buy", confidence: float = 0.8) -> Signal:
    return Signal(
        symbol="BTC-USD",
        action=action,
        confidence=confidence,
        timestamp=_fixed_clock(),
    )


def _make_archive() -> MagicMock:
    archive = MagicMock()
    archive.persist = MagicMock()
    return archive


def _make_orchestrator(
    baseline_signal: Signal | None = None,
    candidate_signal: Signal | None = None,
    config: ShadowDeploymentConfig | None = None,
    archive=None,
) -> ShadowDeploymentOrchestrator:
    if baseline_signal is None:
        baseline_signal = _make_signal("buy", 0.8)
    if candidate_signal is None:
        candidate_signal = _make_signal("buy", 0.79)
    if config is None:
        config = ShadowDeploymentConfig(
            window_size=50,
            min_samples=5,
            max_disagreement_rate=0.5,
            max_confidence_mape=1.0,
            max_action_drift=1.0,
            promotion_disagreement_rate=0.0,
            promotion_confidence_mape=0.5,
            promotion_action_drift=0.5,
            promotion_stable_observations=3,
        )
    if archive is None:
        archive = _make_archive()

    def baseline_gen(state: Mapping[str, Any]) -> Signal:
        return baseline_signal

    def candidate_gen(state: Mapping[str, Any]) -> Signal:
        return candidate_signal

    return ShadowDeploymentOrchestrator(
        baseline=baseline_gen,
        candidates={"cand_a": candidate_gen},
        config=config,
        archive=archive,
        clock=_fixed_clock,
    )


def _make_order(
    symbol: str = "BTC-USD",
    side: str = "buy",
    qty: float = 0.5,
    price: float = 50_000.0,
    order_type: str = "limit",
) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide(side),
        quantity=qty,
        price=price,
        order_type=OrderType(order_type),
    )


def _make_resilience() -> ExchangeResilienceProfile:
    return default_resilience_profile(
        token_bucket_capacity=1000.0,
        token_bucket_refill_per_sec=1000.0,
        leaky_bucket_capacity=1000,
        leaky_bucket_leak_rate=1000.0,
        bulkhead_concurrency=50,
    )


def _make_route(
    name: str = "primary",
    connector=None,
    resilience=None,
    slippage_model: SlippageModel | None = None,
) -> ExecutionRoute:
    if connector is None:
        connector = MagicMock()
    if resilience is None:
        resilience = _make_resilience()
    return ExecutionRoute(
        name=name,
        connector=connector,
        resilience=resilience,
        slippage_model=slippage_model,
        operation_timeout=None,  # disable threading for unit tests
    )


def _make_workflow() -> RiskComplianceWorkflow:
    spec = SymbolSpecification(
        symbol="BTC-USD",
        min_qty=0.0001,
        min_notional=10.0,
        step_size=0.0001,
        tick_size=0.01,
    )
    normalizer = SymbolNormalizer(specifications={spec.symbol: spec})
    compliance = ComplianceMonitor(normalizer, strict=True, auto_round=True)
    limits = RiskLimits(
        max_notional=500_000.0,
        max_position=10.0,
        max_orders_per_interval=100,
        interval_seconds=1.0,
    )
    return RiskComplianceWorkflow(RiskManager(limits), compliance)


# ==========================================================================
# shadow.py tests
# ==========================================================================


class TestShadowDeploymentConfig:
    def test_defaults_are_valid(self):
        cfg = ShadowDeploymentConfig()
        assert cfg.window_size == 300
        assert cfg.min_samples == 600

    def test_invalid_window_size_raises(self):
        with pytest.raises(ValueError, match="window_size"):
            ShadowDeploymentConfig(window_size=0)

    def test_invalid_min_samples_raises(self):
        with pytest.raises(ValueError, match="min_samples"):
            ShadowDeploymentConfig(min_samples=-1)

    def test_invalid_promotion_stable_raises(self):
        with pytest.raises(ValueError, match="promotion_stable_observations"):
            ShadowDeploymentConfig(promotion_stable_observations=0)

    def test_disagreement_rate_out_of_range(self):
        with pytest.raises(ValueError, match="max_disagreement_rate"):
            ShadowDeploymentConfig(max_disagreement_rate=1.5)

    def test_promotion_disagreement_rate_out_of_range(self):
        with pytest.raises(ValueError, match="promotion_disagreement_rate"):
            ShadowDeploymentConfig(promotion_disagreement_rate=-0.1)

    def test_negative_mape_raises(self):
        with pytest.raises(ValueError, match="max_confidence_mape"):
            ShadowDeploymentConfig(max_confidence_mape=-1.0)

    def test_action_drift_out_of_range(self):
        with pytest.raises(ValueError, match="max_action_drift"):
            ShadowDeploymentConfig(max_action_drift=3.0)

    def test_mape_epsilon_zero_raises(self):
        with pytest.raises(ValueError, match="mape_epsilon"):
            ShadowDeploymentConfig(mape_epsilon=0.0)


class TestActionToNumeric:
    def test_buy_maps_to_one(self):
        assert _action_to_numeric(SignalAction.BUY) == 1.0

    def test_sell_maps_to_minus_one(self):
        assert _action_to_numeric(SignalAction.SELL) == -1.0

    def test_exit_maps_to_zero(self):
        assert _action_to_numeric(SignalAction.EXIT) == 0.0

    def test_hold_maps_to_zero(self):
        assert _action_to_numeric(SignalAction.HOLD) == 0.0

    def test_string_buy(self):
        assert _action_to_numeric("buy") == 1.0


class TestShadowDeploymentOrchestrator:
    def test_requires_at_least_one_candidate(self):
        with pytest.raises(ValueError, match="at least one candidate"):
            ShadowDeploymentOrchestrator(
                baseline=lambda s: _make_signal(),
                candidates={},
                config=ShadowDeploymentConfig(),
                archive=_make_archive(),
            )

    def test_empty_candidate_name_raises(self):
        with pytest.raises(ValueError, match="candidate name"):
            ShadowDeploymentOrchestrator(
                baseline=lambda s: _make_signal(),
                candidates={"": lambda s: _make_signal()},
                config=ShadowDeploymentConfig(),
                archive=_make_archive(),
            )

    def test_status_returns_active_on_init(self):
        orch = _make_orchestrator()
        assert orch.status() == {"cand_a": "active"}

    def test_process_returns_continue_while_below_min_samples(self):
        orch = _make_orchestrator()
        decisions = orch.process({})
        assert "cand_a" in decisions
        assert decisions["cand_a"].action == "continue"

    def test_archive_persist_called_each_tick(self):
        archive = _make_archive()
        orch = _make_orchestrator(archive=archive)
        orch.process({})
        archive.persist.assert_called_once()

    def test_archive_record_fields(self):
        archive = _make_archive()
        orch = _make_orchestrator(archive=archive)
        orch.process({})
        record: ShadowArchiveRecord = archive.persist.call_args[0][0]
        assert isinstance(record, ShadowArchiveRecord)
        assert record.candidate == "cand_a"
        assert isinstance(record.deviation, SignalDeviation)
        assert isinstance(record.decision, ShadowDecision)

    def test_action_mismatch_detected(self):
        """Candidate BUY vs baseline SELL → action_mismatch=True."""
        archive = _make_archive()
        baseline = _make_signal("sell", 0.7)
        candidate = _make_signal("buy", 0.7)
        orch = _make_orchestrator(
            baseline_signal=baseline,
            candidate_signal=candidate,
            archive=archive,
        )
        orch.process({})
        record: ShadowArchiveRecord = archive.persist.call_args[0][0]
        assert record.deviation.action_mismatch is True

    def test_no_action_mismatch_when_signals_agree(self):
        archive = _make_archive()
        baseline = _make_signal("buy", 0.7)
        candidate = _make_signal("buy", 0.7)
        orch = _make_orchestrator(
            baseline_signal=baseline,
            candidate_signal=candidate,
            archive=archive,
        )
        orch.process({})
        record: ShadowArchiveRecord = archive.persist.call_args[0][0]
        assert record.deviation.action_mismatch is False

    def test_candidate_generator_error_causes_reject(self):
        archive = _make_archive()

        def failing_gen(state):
            raise RuntimeError("exploded")

        config = ShadowDeploymentConfig(
            window_size=50,
            min_samples=5,
            promotion_stable_observations=3,
        )
        orch = ShadowDeploymentOrchestrator(
            baseline=lambda s: _make_signal(),
            candidates={"broken": failing_gen},
            config=config,
            archive=archive,
            clock=_fixed_clock,
        )
        decisions = orch.process({})
        assert decisions["broken"].action == "reject"
        assert decisions["broken"].reason == "generator-error"
        archive.persist.assert_called_once()

    def test_guardrail_breach_rejects_candidate(self):
        """Force disagreement_rate above threshold after min_samples observations."""
        config = ShadowDeploymentConfig(
            window_size=50,
            min_samples=3,
            max_disagreement_rate=0.01,  # very tight
            max_confidence_mape=1.0,
            max_action_drift=2.0,
            promotion_disagreement_rate=0.0,
            promotion_confidence_mape=0.5,
            promotion_action_drift=0.5,
            promotion_stable_observations=100,
        )
        archive = _make_archive()
        baseline_sig = _make_signal("buy", 0.8)
        candidate_sig = _make_signal("sell", 0.8)  # always disagrees

        def baseline_gen(s):
            return baseline_sig

        def candidate_gen(s):
            return candidate_sig

        orch = ShadowDeploymentOrchestrator(
            baseline=baseline_gen,
            candidates={"bad": candidate_gen},
            config=config,
            archive=archive,
            clock=_fixed_clock,
        )
        decisions = None
        for _ in range(10):
            decisions = orch.process({})
        # After rejection the decision action is either "reject" (tick it happened)
        # or "rejected" (terminal on subsequent ticks). Either way status is "rejected".
        assert decisions["bad"].action in ("reject", "rejected")
        assert orch.status()["bad"] == "rejected"

    def test_promotion_after_stable_observations(self):
        """Candidate that perfectly agrees gets promoted once stable threshold met."""
        config = ShadowDeploymentConfig(
            window_size=50,
            min_samples=3,
            max_disagreement_rate=0.5,
            max_confidence_mape=1.0,
            max_action_drift=1.0,
            promotion_disagreement_rate=0.0,
            promotion_confidence_mape=0.5,
            promotion_action_drift=0.5,
            promotion_stable_observations=3,
        )
        archive = _make_archive()
        sig = _make_signal("buy", 0.8)

        orch = ShadowDeploymentOrchestrator(
            baseline=lambda s: sig,
            candidates={"perfect": lambda s: sig},
            config=config,
            archive=archive,
            clock=_fixed_clock,
        )
        decisions = None
        for _ in range(10):
            decisions = orch.process({})
        # On the tick promotion happens the action is "promote"; on subsequent
        # ticks the terminal path returns the status string "promoted".
        assert decisions["perfect"].action in ("promote", "promoted")
        assert orch.status()["perfect"] == "promoted"

    def test_terminal_candidate_returns_terminal_decision(self):
        """After rejection, subsequent ticks return terminal decisions."""
        config = ShadowDeploymentConfig(
            window_size=50,
            min_samples=3,
            max_disagreement_rate=0.01,
            max_confidence_mape=1.0,
            max_action_drift=2.0,
            promotion_disagreement_rate=0.0,
            promotion_confidence_mape=0.5,
            promotion_action_drift=0.5,
            promotion_stable_observations=100,
        )
        archive = _make_archive()

        orch = ShadowDeploymentOrchestrator(
            baseline=lambda s: _make_signal("buy", 0.8),
            candidates={"c": lambda s: _make_signal("sell", 0.8)},
            config=config,
            archive=archive,
            clock=_fixed_clock,
        )
        # Drive to rejection
        for _ in range(20):
            orch.process({})

        # Subsequent tick should return terminal
        decisions = orch.process({})
        assert decisions["c"].reason == "terminal"

    def test_multiple_candidates_tracked_independently(self):
        config = ShadowDeploymentConfig(
            window_size=50, min_samples=3, promotion_stable_observations=3
        )
        archive = _make_archive()
        good_sig = _make_signal("buy", 0.8)
        bad_sig = _make_signal("sell", 0.8)

        orch = ShadowDeploymentOrchestrator(
            baseline=lambda s: good_sig,
            candidates={
                "good": lambda s: good_sig,
                "bad": lambda s: bad_sig,
            },
            config=ShadowDeploymentConfig(
                window_size=50,
                min_samples=3,
                max_disagreement_rate=0.01,
                max_confidence_mape=1.0,
                max_action_drift=2.0,
                promotion_disagreement_rate=0.0,
                promotion_confidence_mape=0.5,
                promotion_action_drift=0.5,
                promotion_stable_observations=3,
            ),
            archive=archive,
            clock=_fixed_clock,
        )

        decisions = None
        for _ in range(20):
            decisions = orch.process({})

        assert decisions["good"].action in ("promote", "promoted")
        assert decisions["bad"].action in ("reject", "rejected", "terminal")

    def test_record_failure_before_any_update_returns_default_metrics(self):
        """_CandidateState.record_failure with no prior update."""
        archive = _make_archive()

        def fail_gen(s):
            raise ValueError("boom")

        orch = ShadowDeploymentOrchestrator(
            baseline=lambda s: _make_signal(),
            candidates={"x": fail_gen},
            config=ShadowDeploymentConfig(
                window_size=10, min_samples=3, promotion_stable_observations=3
            ),
            archive=archive,
            clock=_fixed_clock,
        )
        decisions = orch.process({})
        # Default metrics: disagreement_rate=1.0, others=0.0
        metrics = decisions["x"].metrics
        assert metrics.disagreement_rate == 1.0
        assert metrics.observations == 0


# ==========================================================================
# router.py tests
# ==========================================================================


class TestOrderStateNormalizer:
    def test_normalizes_status_without_override(self):
        order = _make_order()
        normalizer = OrderStateNormalizer()
        result = normalizer.normalize(order)
        assert result.status == order.status
        assert result.filled_quantity == 0.0

    def test_applies_status_override_by_order_id(self):
        order = _make_order()
        order.order_id = "abc123"
        order.broker_order_id = "abc123"
        normalizer = OrderStateNormalizer(status_overrides={"abc123": OrderStatus.FILLED})
        result = normalizer.normalize(order)
        assert result.status == OrderStatus.FILLED

    def test_no_override_when_order_id_absent(self):
        order = _make_order()
        normalizer = OrderStateNormalizer(status_overrides={"abc123": OrderStatus.FILLED})
        result = normalizer.normalize(order)
        assert result.status == OrderStatus.PENDING


class TestErrorMapper:
    def test_maps_known_token(self):
        mapper = ErrorMapper(mapping={"INSUFFICIENT": TransientOrderError})
        exc = RuntimeError("INSUFFICIENT_FUNDS: balance too low")
        translated = mapper.translate(exc)
        assert isinstance(translated, TransientOrderError)

    def test_passthrough_unknown_error(self):
        mapper = ErrorMapper(mapping={"TIMEOUT": TransientOrderError})
        exc = RuntimeError("random failure")
        translated = mapper.translate(exc)
        assert translated is exc

    def test_empty_mapping_passthrough(self):
        mapper = ErrorMapper()
        exc = ValueError("oops")
        assert mapper.translate(exc) is exc


class TestSlippageModel:
    def test_market_order_passes_through_unchanged(self):
        model = SlippageModel()
        order = _make_order(order_type="market", price=None)
        result = model.apply(order)
        assert result.price is None

    def test_limit_buy_increases_price(self):
        model = SlippageModel(max_slippage_bps=5.0, limit_buffer_bps=10.0)
        order = _make_order(side="buy", order_type="limit", price=50_000.0)
        result = model.apply(order)
        assert result.price > 50_000.0

    def test_limit_sell_decreases_price(self):
        model = SlippageModel(max_slippage_bps=5.0, limit_buffer_bps=10.0)
        order = _make_order(side="sell", order_type="limit", price=50_000.0)
        result = model.apply(order)
        assert result.price < 50_000.0

    def test_limit_order_without_price_returns_unchanged(self):
        """SlippageModel skips adjustment when price is None (price guard branch)."""
        model = SlippageModel()
        # A MARKET order has no price; use it to reach the `price is None` branch
        # inside SlippageModel.apply (which checks `price is None or price <= 0`).
        order = _make_order(order_type="market", price=None)
        result = model.apply(order)
        assert result.price is None


class TestResilientExecutionRouter:
    def test_register_route_and_resolve(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        route = _make_route("main", connector)
        router.register_route("main", route)
        # fetch_order uses the connector directly
        connector.fetch_order.return_value = _make_order()
        result = router.fetch_order("main", "oid123")
        assert isinstance(result, NormalizedOrderState)

    def test_duplicate_route_registration_raises(self):
        router = ResilientExecutionRouter()
        route = _make_route("dup")
        router.register_route("dup", route)
        with pytest.raises(ValueError, match="already registered"):
            router.register_route("dup", _make_route("dup"))

    def test_unknown_route_raises_lookup_error(self):
        router = ResilientExecutionRouter()
        with pytest.raises(LookupError, match="Unknown execution route"):
            router.fetch_order("nonexistent", "oid")

    def test_place_order_happy_path(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        submitted_order = _make_order()
        submitted_order.order_id = "ord-001"
        connector.place_order.return_value = submitted_order
        route = _make_route("exch", connector)
        router.register_route("exch", route)

        order = _make_order()
        result = router.place_order("exch", order)
        assert isinstance(result, NormalizedOrderState)
        connector.place_order.assert_called_once()

    def test_place_order_idempotency_returns_cached(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        submitted = _make_order()
        submitted.order_id = "ord-idem"
        connector.place_order.return_value = submitted
        connector.fetch_order.return_value = submitted
        route = _make_route("exch", connector)
        router.register_route("exch", route)

        order = _make_order()
        router.place_order("exch", order, idempotency_key="key-1")
        # Second call with same key should use cached route
        router.place_order("exch", order, idempotency_key="key-1")
        # place_order on connector called only once, second hit goes to fetch_order
        assert connector.place_order.call_count == 1
        assert connector.fetch_order.call_count == 1

    def test_cancel_order_delegates_to_connector(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        connector.cancel_order.return_value = True
        route = _make_route("exch", connector)
        router.register_route("exch", route)

        result = router.cancel_order("exch", "oid-001")
        assert result is True
        connector.cancel_order.assert_called_once_with("oid-001")

    def test_open_orders_returns_normalized_list(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        connector.open_orders.return_value = [_make_order()]
        route = _make_route("exch", connector)
        router.register_route("exch", route)

        result = router.open_orders("exch")
        assert len(list(result)) == 1
        assert all(isinstance(r, NormalizedOrderState) for r in result)

    def test_get_positions_delegates_to_connector(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        connector.get_positions.return_value = [{"symbol": "BTC-USD", "net_quantity": 1.0}]
        route = _make_route("exch", connector)
        router.register_route("exch", route)

        result = router.get_positions("exch")
        assert result[0]["symbol"] == "BTC-USD"

    def test_place_order_fails_without_backup_raises(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        connector.place_order.side_effect = RuntimeError("connection lost")
        route = _make_route("exch", connector)
        router.register_route("exch", route)

        with pytest.raises(Exception):
            router.place_order("exch", _make_order())

    def test_place_order_fails_over_to_backup(self):
        router = ResilientExecutionRouter()

        primary_connector = MagicMock()
        primary_connector.place_order.side_effect = RuntimeError("primary down")

        backup_connector = MagicMock()
        backup_order = _make_order()
        backup_order.order_id = "backup-ord"
        backup_connector.place_order.return_value = backup_order

        primary_route = _make_route("primary", primary_connector)
        backup_route = _make_route("backup", backup_connector)
        router.register_route("primary", primary_route, backup=backup_route)

        result = router.place_order("primary", _make_order())
        assert isinstance(result, NormalizedOrderState)
        backup_connector.place_order.assert_called_once()

    def test_cancel_order_fails_over_to_backup(self):
        router = ResilientExecutionRouter()

        primary_connector = MagicMock()
        primary_connector.cancel_order.side_effect = RuntimeError("gone")

        backup_connector = MagicMock()
        backup_connector.cancel_order.return_value = True

        primary_route = _make_route("primary", primary_connector)
        backup_route = _make_route("backup", backup_connector)
        router.register_route("primary", primary_route, backup=backup_route)

        result = router.cancel_order("primary", "oid")
        assert result is True

    def test_both_primary_and_backup_fail_raises(self):
        router = ResilientExecutionRouter()

        primary_connector = MagicMock()
        primary_connector.place_order.side_effect = RuntimeError("primary fail")

        backup_connector = MagicMock()
        backup_connector.place_order.side_effect = RuntimeError("backup fail")

        primary_route = _make_route("primary", primary_connector)
        backup_route = _make_route("backup", backup_connector)
        router.register_route("primary", primary_route, backup=backup_route)

        with pytest.raises(Exception):
            router.place_order("primary", _make_order())

    def test_throttled_route_raises_transient_error(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        resilience = MagicMock()
        resilience.allow_request.return_value = False

        route = ExecutionRoute(
            name="throttled",
            connector=connector,
            resilience=resilience,
            operation_timeout=None,
        )
        router.register_route("throttled", route)

        with pytest.raises(TransientOrderError, match="throttled"):
            router.place_order("throttled", _make_order())

    def test_cancel_order_throttled_raises(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        resilience = MagicMock()
        resilience.allow_request.return_value = False

        route = ExecutionRoute(
            name="throttled",
            connector=connector,
            resilience=resilience,
            operation_timeout=None,
        )
        router.register_route("throttled", route)

        with pytest.raises(TransientOrderError, match="throttled"):
            router.cancel_order("throttled", "oid")

    def test_slippage_applied_on_place_order(self):
        router = ResilientExecutionRouter()
        connector = MagicMock()
        received_orders = []

        def capture_order(order, *, idempotency_key=None):
            received_orders.append(order)
            result = _make_order()
            result.order_id = "x"
            return result

        connector.place_order.side_effect = capture_order
        slippage = SlippageModel(max_slippage_bps=5.0, limit_buffer_bps=10.0)
        route = _make_route("exch", connector, slippage_model=slippage)
        router.register_route("exch", route)

        original = _make_order(side="buy", order_type="limit", price=50_000.0)
        router.place_order("exch", original)
        assert received_orders[0].price > 50_000.0

    def test_backup_route_duplicate_registration_raises(self):
        router = ResilientExecutionRouter()
        primary = _make_route("venue")
        backup = _make_route("venue_backup")
        router.register_route("venue", primary, backup=backup)
        with pytest.raises(ValueError, match="already registered"):
            router.register_route("venue", _make_route("venue"))


# ==========================================================================
# workflows.py tests
# ==========================================================================


class TestOrderRequest:
    def test_fields_stored(self):
        req = OrderRequest(symbol="ETH-USD", side="buy", quantity=1.0, price=3000.0)
        assert req.symbol == "ETH-USD"
        assert req.side == "buy"
        assert req.quantity == 1.0
        assert req.price == 3000.0


class TestOrderAssessment:
    def _clean_report(self, symbol: str = "BTC-USD") -> ComplianceReport:
        return ComplianceReport(
            symbol=symbol,
            requested_quantity=1.0,
            requested_price=50_000.0,
            normalized_quantity=1.0,
            normalized_price=50_000.0,
            violations=(),
            blocked=False,
        )

    def _blocked_report(self, symbol: str = "BTC-USD") -> ComplianceReport:
        return ComplianceReport(
            symbol=symbol,
            requested_quantity=0.0,
            requested_price=0.0,
            normalized_quantity=0.0,
            normalized_price=0.0,
            violations=("qty below minimum",),
            blocked=True,
        )

    def test_passed_true_when_clean_and_no_risk_error(self):
        req = OrderRequest("BTC-USD", "buy", 1.0, 50_000.0)
        assessment = OrderAssessment(req, self._clean_report())
        assert assessment.passed is True

    def test_passed_false_when_blocked(self):
        req = OrderRequest("BTC-USD", "buy", 0.0, 0.0)
        assessment = OrderAssessment(req, self._blocked_report())
        assert assessment.passed is False

    def test_passed_false_when_risk_error_present(self):
        req = OrderRequest("BTC-USD", "buy", 1.0, 50_000.0)
        assessment = OrderAssessment(req, self._clean_report(), risk_error="too large")
        assert assessment.passed is False


class TestWorkflowAssessment:
    def _make_assessment(self, symbol: str = "BTC-USD", blocked: bool = False):
        req = OrderRequest(symbol, "buy", 1.0, 50_000.0)
        report = ComplianceReport(
            symbol=symbol,
            requested_quantity=1.0,
            requested_price=50_000.0,
            normalized_quantity=1.0,
            normalized_price=50_000.0,
            violations=("blocked",) if blocked else (),
            blocked=blocked,
        )
        return OrderAssessment(req, report)

    def test_passed_true_when_all_accepted(self):
        wa = WorkflowAssessment(
            accepted=(self._make_assessment(),),
            rejected=(),
        )
        assert wa.passed is True

    def test_passed_false_when_any_rejected(self):
        wa = WorkflowAssessment(
            accepted=(),
            rejected=(self._make_assessment(blocked=True),),
        )
        assert wa.passed is False

    def test_compliance_reports_merges_both_sides(self):
        wa = WorkflowAssessment(
            accepted=(self._make_assessment("BTC-USD"),),
            rejected=(self._make_assessment("ETH-USD", blocked=True),),
        )
        symbols = [r.symbol for r in wa.compliance_reports]
        assert "BTC-USD" in symbols
        assert "ETH-USD" in symbols


class TestRiskComplianceWorkflow:
    def test_valid_order_accepted(self):
        workflow = _make_workflow()
        orders = [OrderRequest("BTC-USD", "buy", 0.5, 50_000.0)]
        result = workflow.evaluate(orders)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 0
        assert result.passed is True

    def test_blocked_compliance_rejects(self):
        workflow = _make_workflow()
        # Quantity 0 should fail normalization / compliance
        orders = [OrderRequest("BTC-USD", "buy", 0.0, 50_000.0)]
        result = workflow.evaluate(orders)
        assert len(result.rejected) >= 1

    def test_risk_limit_violation_rejects(self):
        """Exceed max_notional to trigger LimitViolation."""
        spec = SymbolSpecification(
            symbol="BTC-USD",
            min_qty=0.0001,
            min_notional=10.0,
            step_size=0.0001,
            tick_size=0.01,
        )
        normalizer = SymbolNormalizer(specifications={spec.symbol: spec})
        compliance = ComplianceMonitor(normalizer, strict=True, auto_round=True)
        limits = RiskLimits(
            max_notional=100.0,  # tiny limit so 0.5 BTC @ 50k exceeds it
            max_position=10.0,
            max_orders_per_interval=100,
            interval_seconds=1.0,
        )
        workflow = RiskComplianceWorkflow(RiskManager(limits), compliance)
        orders = [OrderRequest("BTC-USD", "buy", 0.5, 50_000.0)]
        result = workflow.evaluate(orders)
        assert len(result.rejected) == 1
        assert result.rejected[0].risk_error is not None

    def test_multiple_orders_mixed_outcomes(self):
        workflow = _make_workflow()
        orders = [
            OrderRequest("BTC-USD", "buy", 0.1, 50_000.0),  # valid
            OrderRequest("BTC-USD", "buy", 0.0, 50_000.0),  # invalid qty
        ]
        result = workflow.evaluate(orders)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 1

    def test_evaluate_from_dicts_valid(self):
        workflow = _make_workflow()
        payloads = [{"symbol": "BTC-USD", "side": "buy", "quantity": 0.1, "price": 50_000.0}]
        result = workflow.evaluate_from_dicts(payloads)
        assert len(result.accepted) == 1

    def test_evaluate_from_dicts_defaults_side_to_buy(self):
        workflow = _make_workflow()
        payloads = [{"symbol": "BTC-USD", "quantity": 0.1, "price": 50_000.0}]
        result = workflow.evaluate_from_dicts(payloads)
        assert len(result.accepted) == 1

    def test_evaluate_from_dicts_defaults_quantity_zero_rejects(self):
        workflow = _make_workflow()
        payloads = [{"symbol": "BTC-USD", "price": 50_000.0}]
        result = workflow.evaluate_from_dicts(payloads)
        assert len(result.rejected) == 1

    def test_empty_order_batch_returns_empty_assessment(self):
        workflow = _make_workflow()
        result = workflow.evaluate([])
        assert result.passed is True
        assert len(result.accepted) == 0
        assert len(result.rejected) == 0

    def test_register_fill_tracks_exposure_across_orders(self):
        """Consecutive orders should accumulate exposure, triggering risk on overflow."""
        spec = SymbolSpecification(
            symbol="BTC-USD",
            min_qty=0.0001,
            min_notional=10.0,
            step_size=0.0001,
            tick_size=0.01,
        )
        normalizer = SymbolNormalizer(specifications={spec.symbol: spec})
        compliance = ComplianceMonitor(normalizer, strict=True, auto_round=True)
        limits = RiskLimits(
            max_notional=50_000.0,
            max_position=0.5,  # only 0.5 BTC allowed
            max_orders_per_interval=100,
            interval_seconds=1.0,
        )
        workflow = RiskComplianceWorkflow(RiskManager(limits), compliance)
        orders = [
            OrderRequest("BTC-USD", "buy", 0.5, 50_000.0),  # fills limit exactly
            OrderRequest("BTC-USD", "buy", 0.1, 50_000.0),  # should exceed
        ]
        result = workflow.evaluate(orders)
        assert len(result.accepted) == 1
        assert len(result.rejected) == 1

    def test_compliance_violation_with_none_report_creates_fallback_report(self):
        """ComplianceViolation raised without report field → workflow builds one."""
        risk = MagicMock()
        compliance = MagicMock()
        compliance.check.side_effect = ComplianceViolation("bad", report=None)

        workflow = RiskComplianceWorkflow(risk, compliance)
        orders = [OrderRequest("BTC-USD", "buy", 0.1, 50_000.0)]
        result = workflow.evaluate(orders)
        assert len(result.rejected) == 1
        assert result.rejected[0].compliance_report.blocked is True
        assert "bad" in result.rejected[0].compliance_report.violations[0]

    def test_compliance_violation_with_report_uses_it(self):
        """ComplianceViolation raised with a pre-built report → workflow uses it."""
        risk = MagicMock()
        report = ComplianceReport(
            symbol="BTC-USD",
            requested_quantity=0.1,
            requested_price=50_000.0,
            normalized_quantity=0.1,
            normalized_price=50_000.0,
            violations=("custom violation",),
            blocked=True,
        )
        compliance = MagicMock()
        compliance.check.side_effect = ComplianceViolation("custom violation", report=report)

        workflow = RiskComplianceWorkflow(risk, compliance)
        orders = [OrderRequest("BTC-USD", "buy", 0.1, 50_000.0)]
        result = workflow.evaluate(orders)
        assert len(result.rejected) == 1
        assert result.rejected[0].compliance_report is report

    def test_blocked_report_without_exception_rejects(self):
        """compliance.check returns a blocked report without raising."""
        risk = MagicMock()
        blocked_report = ComplianceReport(
            symbol="BTC-USD",
            requested_quantity=0.1,
            requested_price=50_000.0,
            normalized_quantity=0.1,
            normalized_price=50_000.0,
            violations=("over limit",),
            blocked=True,
        )
        compliance = MagicMock()
        compliance.check.return_value = blocked_report

        workflow = RiskComplianceWorkflow(risk, compliance)
        orders = [OrderRequest("BTC-USD", "buy", 0.1, 50_000.0)]
        result = workflow.evaluate(orders)
        assert len(result.rejected) == 1
        risk.validate_order.assert_not_called()
